#!/usr/bin/env python3
"""Minimal GET-only Portainer MCP server.

This server intentionally exposes only three read-only tools and only talks to
Portainer with HTTP GET requests. Portainer CE does not provide a true granular
read-only RBAC boundary for this use case, so this code is the enforcement
boundary. Keep it boring.
"""

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Optional

from mcp.server.fastmcp import FastMCP

PORTAINER_URL = os.environ.get("PORTAINER_URL", "https://<gateway-host>:9443").rstrip("/")
TOKEN_FILE = os.environ.get("PORTAINER_TOKEN_FILE", "/run/secrets/portainer_api_token")
ALLOWED_ENDPOINTS = {
    int(x)
    for x in os.environ.get("PORTAINER_ALLOWED_ENDPOINTS", "2,3").split(",")
    if x.strip()
}
TLS_VERIFY = os.environ.get("PORTAINER_TLS_VERIFY", "false").lower() in (
    "1",
    "true",
    "yes",
)
_CTX = None if TLS_VERIFY else ssl._create_unverified_context()

API_KEY = os.environ.get("PORTAINER_API_KEY")
if not API_KEY:
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        API_KEY = f.read().strip()

mcp = FastMCP("portainer-readonly")


def _p_get(path: str):
    """Call the Portainer API with GET only."""
    if not path.startswith("/"):
        path = "/" + path
    req = urllib.request.Request(
        PORTAINER_URL + path,
        headers={"X-API-Key": API_KEY},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=30) as r:
            txt = r.read().decode("utf-8", "replace")
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Portainer GET {path} failed HTTP {e.code}: {body}") from e


def _status_text(v):
    return {1: "active", 2: "inactive", 3: "deploying", 4: "error"}.get(
        v, "unknown"
    )


@mcp.tool()
def list_stacks(endpoint_id: Optional[int] = None) -> dict:
    """List Portainer stacks for the allowed endpoint IDs only."""
    if endpoint_id is not None and endpoint_id not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint_id is not allowed")

    stacks = _p_get("/api/stacks") or []
    out = []
    for stack in stacks:
        eid = stack.get("EndpointId")
        if eid not in ALLOWED_ENDPOINTS:
            continue
        if endpoint_id is not None and eid != endpoint_id:
            continue
        out.append(
            {
                "id": stack.get("Id"),
                "name": stack.get("Name"),
                "endpoint_id": eid,
                "status": stack.get("Status"),
                "status_text": _status_text(stack.get("Status")),
                "type": stack.get("Type"),
                "project_path": stack.get("ProjectPath"),
            }
        )
    return {
        "stacks": out,
        "count": len(out),
        "allowed_endpoints": sorted(ALLOWED_ENDPOINTS),
    }


@mcp.tool()
def get_stack_status(stack_id: int) -> dict:
    """Get status for one Portainer stack by stack_id."""
    stacks = _p_get("/api/stacks") or []
    for stack in stacks:
        if stack.get("Id") == stack_id:
            eid = stack.get("EndpointId")
            if eid not in ALLOWED_ENDPOINTS:
                raise ValueError("stack endpoint is not allowed")
            return {
                "id": stack.get("Id"),
                "name": stack.get("Name"),
                "endpoint_id": eid,
                "status": stack.get("Status"),
                "status_text": _status_text(stack.get("Status")),
                "type": stack.get("Type"),
                "project_path": stack.get("ProjectPath"),
            }
    raise ValueError("stack not found or not visible")


@mcp.tool()
def list_containers(endpoint_id: int = 2, all: bool = True) -> dict:
    """List containers from an allowed Portainer endpoint via GET-only Docker proxy."""
    if endpoint_id not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint_id is not allowed")

    containers = (
        _p_get(
            f"/api/endpoints/{endpoint_id}/docker/containers/json?all={'true' if all else 'false'}"
        )
        or []
    )
    out = []
    for container in containers:
        labels = container.get("Labels") or {}
        health = (container.get("Health") or {}).get("Status")
        out.append(
            {
                "id": (container.get("Id") or "")[:12],
                "names": container.get("Names") or [],
                "image": container.get("Image"),
                "state": container.get("State"),
                "status": container.get("Status"),
                "health": health,
                "compose_project": labels.get("com.docker.compose.project"),
                "compose_service": labels.get("com.docker.compose.service"),
                "ports": container.get("Ports") or [],
            }
        )
    return {"endpoint_id": endpoint_id, "containers": out, "count": len(out)}


if __name__ == "__main__":
    mcp.run()
