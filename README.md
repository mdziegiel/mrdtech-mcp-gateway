# Portainer MCP Gateway

Minimal Docker MCP Gateway deployment for read-only Portainer observability.

This repository contains a small custom MCP server that exposes exactly three tools through Docker MCP Gateway:

- `list_stacks`
- `get_stack_status`
- `list_containers`

No write, update, restart, delete, deploy, or generic Portainer proxy tool is exposed.

## Architecture

```text
Hermes / MCP client on <agent-host>
  -> local HTTP MCP endpoint http://127.0.0.1:18811/mcp
  -> persistent SSH tunnel
  -> <user>@<gateway-host>
  -> 127.0.0.1:8811 on <gateway-host>
  -> Docker MCP Gateway
  -> custom Portainer read-only MCP server
  -> Portainer API at https://<gateway-host>:9005
```

The gateway host publishes Docker MCP Gateway only on loopback:

```yaml
ports:
  - "127.0.0.1:8811:8811"
```

Clients should connect through an SSH tunnel, not a LAN-exposed listener:

```bash
ssh -N -T \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18811:127.0.0.1:8811 \
  <user>@<gateway-host>
```

A user-level systemd unit example is included at:

```text
systemd/mcp-portainer-ro-tunnel.service
```

## Threat model summary

Portainer CE does **not** provide true granular read-only RBAC for this pattern. A Portainer service account may still need enough Portainer visibility to read existing stacks and containers, especially when existing resources are admin-owned or hidden behind Portainer resource controls.

Therefore the read-only guarantee is enforced at the MCP server code layer:

- the MCP server registers only three tools;
- the Portainer helper performs only HTTP `GET` requests;
- allowed endpoint IDs are explicitly allowlisted with `PORTAINER_ALLOWED_ENDPOINTS`;
- no generic API proxy is exposed;
- no stack update, container restart, delete, deploy, or mutation path exists in the MCP tool surface.

Defense-in-depth controls:

- Docker MCP Gateway bound to `127.0.0.1` only on the gateway host;
- access over SSH local-forward tunnel from the agent host;
- gateway and MCP server containers use `read_only: true`;
- `cap_drop: [ALL]`;
- `security_opt: no-new-privileges:true`;
- dedicated internal Docker network;
- Portainer API token mounted as a file under `./secrets/portainer_api_token`, never committed.

## Files

```text
README.md
Dockerfile
app/server.py
gateway/catalog.yaml
docker-compose.yml.example
systemd/mcp-portainer-ro-tunnel.service
LICENSE
```

## Setup notes

1. Create a Portainer service account such as `hermes-mcp-ro`.
2. Store its API token on the gateway host only:

   ```bash
   mkdir -p secrets
   chmod 700 secrets
   install -m 600 /dev/null secrets/portainer_api_token
   # paste token value into secrets/portainer_api_token without committing it
   ```

3. Copy the example compose file:

   ```bash
   cp docker-compose.yml.example docker-compose.yml
   ```

4. Replace placeholders:

   - `<gateway-host>`: the gateway/Portainer host reachable from inside the containers
   - `<agent-host>`: the MCP client/agent host, used only in documentation
   - `<user>`: SSH account used for the tunnel

5. Deploy on the gateway host:

   ```bash
   docker compose up -d --build
   ```

6. Install and enable the systemd tunnel unit on the agent host:

   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/mcp-portainer-ro-tunnel.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now mcp-portainer-ro-tunnel.service
   loginctl enable-linger "$USER"
   ```

7. Configure Hermes or another MCP client to use:

   ```text
   http://127.0.0.1:18811/mcp
   ```

## Validation commands

List tools through your MCP client and confirm exactly:

```text
get_stack_status
list_containers
list_stacks
```

Confirm the gateway is not LAN-exposed:

```bash
ss -ltnp | grep ':8811'
# expected: 127.0.0.1:8811 only
```

Confirm the SSH tunnel is up on the agent host:

```bash
systemctl --user is-active mcp-portainer-ro-tunnel.service
ss -ltnp | grep '127.0.0.1:18811'
```

## Security warning

Do not commit real values for:

- Portainer API tokens;
- gateway auth tokens;
- `.env` files;
- SSH private keys;
- real internal IP addresses or hostnames;
- production stack paths that reveal private topology.

This repository intentionally uses placeholders such as `<gateway-host>`, `<agent-host>`, and `<user>`.
