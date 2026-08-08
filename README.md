# mrdtech-mcp-gateway

Hardened, read-only MCP gateway for MRDTech infrastructure visibility.

This project publishes a loopback-only Docker MCP Gateway on the gateway host and exposes six read-only backends to Hermes over a persistent SSH tunnel. The design goal is simple: give the agent visibility without giving it the kind of write access that causes avoidable damage.

## Current topology

```text
Hermes on <agent-host>
  -> http://127.0.0.1:18811/mcp
  -> persistent SSH tunnel
  -> 127.0.0.1:8811 on <gateway-host>
  -> Docker MCP Gateway
  -> six read-only MCP servers
```

## Server inventory

| Server | Tool count | Scope |
|---|---:|---|
| `portainer-readonly` | 3 | Portainer stack, stack status, and container inventory visibility |
| `github-readonly` | 28 | Read-only GitHub context, repositories, issues, pull requests, and Actions visibility |
| `filesystem-readonly` | 9 | Read-only access to approved filesystem paths |
| `proxmox-readonly` | 153 | Proxmox VE read/list/get/status visibility |
| `pbs-readonly` | 7 | Proxmox Backup Server datastore, snapshot, verification, GC, and task-log visibility |
| `vault-readonly` | 2 | Obsidian vault RAG search and document retrieval |
| **Total** | **202** | Hard-allowlisted tools behind the gateway |

## Security model

- Gateway listener is bound to loopback on the gateway host and is reached through SSH local-forwarding only.
- Credentials live only in gateway-owned secret storage on the gateway host.
- Hermes connects with HTTP `Authorization` headers carrying `Bearer <token>` on all six MCP entries.
- Docker MCP Gateway hard-allowlists the exact exposed tools; destructive tools are excluded at the gateway layer.
- Where the platform supports it, read-only service accounts back the MCP layer as additional defense in depth.
- Filesystem access is mounted read-only and constrained to approved paths.

## Auth-token enforcement update

On **2026-07-30**, the gateway authentication hardening was completed:

- `MCP_GATEWAY_AUTH_TOKEN` became the enforced gateway auth variable.
- `--allow-unauthenticated` was removed from the live gateway deployment.
- All six Hermes MCP entries were updated to send a Bearer token in the HTTP `Authorization` header.
- Unauthenticated requests to the gateway now return `401 Unauthorized`.

## GitHub PAT rotation

On **2026-08-08**, the fine-grained GitHub PAT used by `github-readonly` was rotated with the same read-only scope as before.

Preserved scope:

- selected repositories only
- repository metadata: read
- contents: read
- issues: read
- pull requests: read
- actions: read

## Origin

This project was built after the July 2026 Portainer compose-path incident. The entire point is to keep infrastructure visibility available without exposing restart, delete, deploy, or generic write capability to the agent.

## Validation expectations

A healthy deployment should satisfy all of the following:

- local tunnel endpoint on the agent host responds at `http://127.0.0.1:18811/mcp`
- unauthenticated MCP POSTs receive `401 Unauthorized`
- authenticated requests succeed with the Bearer token
- only the intended read-only tool surface is exposed
- six-server smoke test passes:
  - `list_stacks`
  - `get_me`
  - `list_allowed_directories`
  - `get_version`
  - `list_datastores`
  - `search_vault`

## Secret-handling rules

Do not commit or publish:

- gateway auth tokens
- GitHub PATs
- `.env` files with real values
- internal hostnames/IPs
- SSH private keys
- production-only secret paths

This repository intentionally uses placeholders such as `<gateway-host>` and `<agent-host>` where public-safe documentation is sufficient.
