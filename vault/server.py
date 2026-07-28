#!/usr/bin/env python3
"""MRDTech Vault RAG read-only MCP server.

Hard-restricted wrapper around the existing vault_search.py logic:
- POST query to Ollama embed endpoint on the configured Ollama host.
- POST vector search / scroll requests to the fixed Qdrant mrdtech_vault collection on the configured Qdrant host.
No arbitrary URLs, collections, methods, filesystem access, shell execution, or write endpoints.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

OLLAMA_EMBED_URL = "http://<OLLAMA_HOST>:11434/api/embed"
OLLAMA_MODEL = "nomic-embed-text"
QDRANT_SEARCH_URL = "http://<QDRANT_HOST>:6333/collections/mrdtech_vault/points/search"
QDRANT_SCROLL_URL = "http://<QDRANT_HOST>:6333/collections/mrdtech_vault/points/scroll"

MAX_SEARCH_LIMIT = 50
MAX_DOCUMENT_CHUNKS = 1000

mcp = FastMCP("vault-readonly")


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    """POST JSON to one of the fixed internal endpoints."""
    if url not in {OLLAMA_EMBED_URL, QDRANT_SEARCH_URL, QDRANT_SCROLL_URL}:
        raise RuntimeError("Endpoint is not allowlisted")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"HTTP {resp.status}: {body[:500]}")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from fixed endpoint: {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for fixed endpoint: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from fixed endpoint: {exc}") from exc


def embed_query(query: str) -> list[float]:
    obj = post_json(OLLAMA_EMBED_URL, {"model": OLLAMA_MODEL, "input": query})
    emb = obj.get("embedding")
    if emb is None:
        embeddings = obj.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            emb = embeddings[0]
    if not isinstance(emb, list) or not emb:
        raise RuntimeError(f"Embedding API returned no embedding; keys={sorted(obj.keys())}")
    return emb


def payload_text(payload: dict[str, Any]) -> str:
    for key in ("text", "chunk_text", "content", "page_content", "body"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def normalize_limit(limit: int) -> int:
    try:
        n = int(limit)
    except Exception as exc:
        raise ValueError("limit must be an integer") from exc
    if n < 1:
        raise ValueError("limit must be >= 1")
    return min(n, MAX_SEARCH_LIMIT)


@mcp.tool()
def search_vault(query: str, limit: int = 5, min_score: float = 0.45) -> dict[str, Any]:
    """Search the MRDTech vault RAG corpus. Read-only: embeds query and searches fixed Qdrant collection."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    lim = normalize_limit(limit)
    threshold = float(min_score)

    vector = embed_query(query.strip())
    search = post_json(
        QDRANT_SEARCH_URL,
        {
            "vector": vector,
            "limit": lim,
            "with_payload": True,
        },
    )
    results = search.get("result")
    if not isinstance(results, list):
        raise RuntimeError(f"Qdrant response missing result list; keys={sorted(search.keys())}")

    out: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        score = float(item.get("score") or 0.0)
        if score < threshold:
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        source_path = payload.get("source_path") or payload.get("path") or payload.get("source") or "(unknown)"
        out.append(
            {
                "score": score,
                "source_path": source_path,
                "heading": payload.get("heading") or payload.get("title") or "",
                "chunk_index": payload.get("chunk_index"),
                "text": payload_text(payload),
            }
        )
    return {"query": query.strip(), "limit": lim, "min_score": threshold, "results": out, "count": len(out)}


@mcp.tool()
def get_document(source_path: str, max_chars: int = 50000) -> dict[str, Any]:
    """Reconstruct one indexed vault document from Qdrant chunks by source_path. Read-only scroll only."""
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("source_path must be a non-empty string")
    src = source_path.strip()
    max_len = int(max_chars)
    if max_len < 1000:
        raise ValueError("max_chars must be >= 1000")

    chunks: list[dict[str, Any]] = []
    offset: Optional[Any] = None
    while len(chunks) < MAX_DOCUMENT_CHUNKS:
        payload: dict[str, Any] = {
            "limit": min(100, MAX_DOCUMENT_CHUNKS - len(chunks)),
            "with_payload": True,
            "with_vector": False,
            "filter": {"must": [{"key": "source_path", "match": {"value": src}}]},
        }
        if offset is not None:
            payload["offset"] = offset
        page = post_json(QDRANT_SCROLL_URL, payload, timeout=30)
        result = page.get("result") if isinstance(page, dict) else None
        points = result.get("points") if isinstance(result, dict) else None
        if not isinstance(points, list):
            raise RuntimeError("Qdrant scroll response missing points list")
        for point in points:
            pl = point.get("payload") if isinstance(point, dict) and isinstance(point.get("payload"), dict) else {}
            chunks.append(
                {
                    "chunk_index": pl.get("chunk_index"),
                    "heading": pl.get("heading") or pl.get("title") or "",
                    "text": payload_text(pl),
                }
            )
        offset = result.get("next_page_offset") if isinstance(result, dict) else None
        if not offset or not points:
            break

    def sort_key(chunk: dict[str, Any]) -> tuple[int, int]:
        idx = chunk.get("chunk_index")
        if isinstance(idx, int):
            return (0, idx)
        try:
            return (0, int(idx))
        except Exception:
            return (1, 0)

    chunks.sort(key=sort_key)
    text = "\n\n".join(chunk["text"] for chunk in chunks if chunk.get("text"))
    truncated = len(text) > max_len
    if truncated:
        text = text[:max_len]

    return {
        "source_path": src,
        "chunk_count": len(chunks),
        "truncated": truncated,
        "max_chars": max_len,
        "text": text,
        "chunks": chunks[:20],
    }


if __name__ == "__main__":
    mcp.run()
