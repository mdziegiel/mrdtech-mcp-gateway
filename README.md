# MRDTech MCP Gateway

A Docker MCP Gateway deployment that exposes five read-only MCP servers through one loopback-bound gateway and one SSH tunnel.

This repository is a sanitized public template. It intentionally contains no real IP addresses, hostnames, API tokens, GitHub PATs, Portainer tokens, Proxmox tokens, or PBS tokens.

## Architecture

```text
Hermes Agent / MCP client
  -> http://127.0.0.1:18811/mcp
  -> SSH tunnel to <GATEWAY_HOST>:127.0.0.1:8811
  -> Docker MCP Gateway
       -> portainer-readonly
       -> github-readonly
       -> filesystem-readonly
       -> proxmox-readonly
       -> pbs-readonly
```

The gateway container binds only to loopback on the Docker host:

```yaml
ports:
  - "127.0.0.1:8811:8811"
```

Clients reach it through a local SSH tunnel, not by exposing the MCP gateway on the LAN or internet.

## Read-only servers

### Portainer

Custom FastMCP server in `app/server.py`.

- Uses Portainer API through GET-only wrapper logic.
- Exposes only:
  - `list_stacks`
  - `get_stack_status`
  - `list_containers`
- Keeps the Portainer token in `secrets/portainer_api_token` on the gateway host.
- No Docker proxy write tools are registered.

### GitHub

Uses the official GitHub MCP image.

- Runs with `GITHUB_READ_ONLY=1`.
- Uses read-only toolsets: `context,repos,issues,pull_requests,actions`.
- Uses a fine-grained PAT scoped to selected repositories with read-only permissions.
- PAT lives only in `secrets/github.env` on the gateway host.

### Filesystem

Thin image built from the official filesystem MCP npm package.

- Mounts only approved host paths as read-only.
- First-pass example mounts compose files as `/projects:ro`.
- Exposes only read/list/search tools.
- Blocks write tools at two layers: Docker read-only bind mount and gateway tool allowlist.

### Proxmox VE

Uses `mcp/proxmox:latest` / GethosTheWalrus Proxmox MCP behind a hard gateway allowlist.

- Uses a dedicated Proxmox API token with audit-only privileges.
- Explicitly excludes `proxmox_api_raw`.
- Excludes create/update/delete/start/stop/migrate/clone/rollback/RBAC-write tools.
- Relies on Proxmox RBAC as the real API-level safety boundary, not MCP descriptions.

### Proxmox Backup Server

Custom FastMCP server in `pbs/server.py`.

- Uses PBS REST API with GET-only wrapper logic.
- Exposes exactly:
  - `list_datastores`
  - `get_datastore_status`
  - `list_snapshots`
  - `get_snapshot_verification_status`
  - `get_gc_status`
  - `list_gc_tasks`
  - `get_task_log`
- PBS token uses `DatastoreAudit` on `/datastore/<store>` and `Audit` on `/system/tasks`.
- Does not grant `Datastore.Read`, `Datastore.Verify`, `Datastore.Modify`, Admin, or PowerUser.

## Security philosophy

The design is defense-in-depth. Gateway filtering alone is not treated as a security boundary because that would be stupid.

Each backend uses as many layers as the platform allows:

1. Credential scoping: dedicated API users/tokens with minimal privileges.
2. Tool allowlisting: Docker MCP Gateway starts with explicit `--tools=<server>:<tool>` entries.
3. Client filtering: Hermes uses logical MCP entries with `tools.include` per backend.
4. OS/API enforcement: read-only bind mounts for filesystem access; RBAC write-denial verification for Proxmox and PBS.
5. Negative testing: destructive tools are called during verification and must return `unknown tool`, not merely be absent from documentation.

## Repository layout

```text
app/server.py                       # Portainer read-only MCP server
pbs/server.py                       # PBS read-only MCP server
filesystem/Dockerfile               # Filesystem MCP image wrapper
Dockerfile.portainer                # Portainer MCP image
pbs/Dockerfile                      # PBS MCP image
gateway/catalog.yaml                # Docker MCP Gateway static catalog
docker-compose.yml.example          # Sanitized compose template
systemd/mrdtech-mcp-gateway-tunnel.service
secrets/README.md                   # Secret-file contract, placeholders only
```

## Deployment notes

1. Copy `docker-compose.yml.example` to `docker-compose.yml` on the gateway host.
2. Replace placeholders such as `<GATEWAY_HOST>`, `<PORTAINER_HOST>`, `<PROXMOX_HOST>`, `<PBS_HOST>`, and `<SSH_USER>`.
3. Create the secret files described in `secrets/README.md` with mode `0600`.
4. Start the gateway stack:

```bash
docker compose build
docker compose up -d
```

5. Configure a local tunnel using the systemd unit example.
6. Configure MCP clients to use `http://127.0.0.1:18811/mcp` and filter tools per logical backend.

## Verification checklist

Before trusting the deployment:

- `docker compose config` passes.
- Gateway logs show all intended servers initialized.
- Gateway tool list contains only approved tools for each backend.
- Calls to destructive tools such as `write_file`, `create_or_update_file`, `proxmox_api_raw`, `run_gc`, and `prune` return `unknown tool`.
- Filesystem writes fail at the OS layer on read-only mounts.
- Proxmox and PBS tokens receive HTTP 403 on write-class API calls.
- Public repo scans show no real IPs, hostnames, usernames, tokens, or secrets.
