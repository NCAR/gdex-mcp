# GDEX MCP Server

An MCP (Model Context Protocol) server exposing the [GDEX](https://gdex.ucar.edu)
(Geoscience Data Exchange) REST API as tools for LLM clients — dataset
discovery/metadata, file listings, data access links, ARCO variables,
portal/dataset metrics, staff contacts, and authenticated subsetting-request
workflows.

## Running locally

```
pip install -e .
gdex-mcp
```

Then point your MCP client (Claude Desktop, Claude Code, etc.) at the
`gdex-mcp` command. Configuration is via environment variables or a `.env`
file — see `CLAUDE.md`'s Configuration section. Most tools need no
configuration at all; set `GDEX_TOKEN` only if you'll use the
subsetting-request tools (`list_request_statuses`, `check_request_status`,
`get_request_files`, `submit_subset_request`, `submit_and_wait_for_request`,
`purge_request`).

## Running as a shared service

Set `GDEX_MCP_TRANSPORT=streamable-http` (see `Dockerfile`) to run this as a
network-reachable service instead of a local stdio subprocess. In that mode,
callers using the subsetting-request tools pass their own GDEX token as an
`Authorization: Token <token>` header on each request rather than relying on
a shared `GDEX_TOKEN` — see CLAUDE.md's "Two transports" section for how
that's wired.

## Docker

```bash
# Build the image
docker build -t gdex-mcp .

# Run the container
docker run -d --name gdex-mcp -p 8080:8080 gdex-mcp
```

MCP requests go to `http://localhost:8080/mcp`.

```bash
# Stop and remove the container
docker stop gdex-mcp && docker rm gdex-mcp
```

## Deployment

A merged PR to `main` triggers the GitHub Actions workflow, which runs the
test suite (`pip install -e ".[test]" && pytest`) and then builds a
new Docker image and pushes it to Harbor
(`hub.k8s.ucar.edu/gdex_mcp/gdex-mcp`). The app is deployed to
Kubernetes via the Helm chart in `app-chart/` — see CLAUDE.md's Deployment
section for how this follows gdex-web-services' conventions.

```bash
# Deploy with Helm
helm upgrade --install gdex-mcp ./app-chart -n <namespace>

# Deploy a test instance
helm upgrade --install gdex-mcp ./app-chart -n <namespace> --set testName=<your-name>
```

## MCP Registry

`gdex-mcp` is published to the official [MCP Registry](https://registry.modelcontextprotocol.io)
as `io.github.rpconroy/gdex-mcp` (see `server.json`), not `io.github.NCAR/gdex-mcp`.
Publishing under the `NCAR` org namespace kept failing with a 403 even after
making org membership public — a known, unresolved issue with the registry's
org-membership check (see [modelcontextprotocol/registry#1537](https://github.com/modelcontextprotocol/registry/issues/1537)
and [#1649](https://github.com/modelcontextprotocol/registry/issues/1649)),
suspected to be an org-admin-side GitHub OAuth App access restriction rather
than anything on our end. `.github/workflows/publish-mcp-registry.yaml`
publishes new versions on `v*` tags; it uses PAT auth (`MCP_GITHUB_TOKEN`
secret) instead of GitHub OIDC because this repo is NCAR-owned, so Actions
OIDC always asserts `repository_owner: NCAR` and can't authenticate as the
personal `rpconroy` namespace. Once NCAR org access is sorted out, moving to
`io.github.NCAR/gdex-mcp` means publishing a new registry entry (the registry
has no rename support) and switching the workflow back to `login github-oidc`.

## Documentation

`CLAUDE.md` has the full picture: architecture, conventions to follow when
adding tools, the two transport modes, and deployment. Read it before making
changes here.
