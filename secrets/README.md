# Secret files

Do not commit real secret files. On the gateway host, create these files with mode `0600`:

- `gateway_auth_token` - Docker MCP Gateway bearer token if authentication is enabled.
- `portainer_api_token` - Portainer API token used only by `portainer-readonly`.
- `github.env` - contains `GITHUB_PERSONAL_ACCESS_TOKEN=<github-fine-grained-pat>`.
- `proxmox.env` - contains `PROXMOX_HOST=https://<PROXMOX_HOST>:8006`, `PROXMOX_USER=root@pam`, `PROXMOX_TOKEN_ID=root@pam!proxmox-mcp-ro`, `PROXMOX_TOKEN_SECRET=<proxmox-token-secret>`.
- `pbs.env` - contains `PBS_URL=https://<PBS_HOST>:8007`, `PBS_TOKEN_ID=pbs-mcp-ro@pbs!pbs-mcp-ro`, `PBS_TOKEN_SECRET=<pbs-token-secret>`, `PBS_DEFAULT_DATASTORE=Backups`.

The public repository intentionally stores placeholders only. Real tokens stay in gateway-owned secret storage on the Docker host.
