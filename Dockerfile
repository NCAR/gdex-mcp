# syntax=docker/dockerfile:1
#
# Runs gdex-mcp as a shared, network-reachable service (streamable-http
# transport) rather than the local stdio subprocess a single desktop/CLI
# client would launch directly. See app-chart/ for the Kubernetes Deployment
# that runs this image, and CLAUDE.md's Configuration section for what each
# env var below does.

FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8080

ENV GDEX_MCP_TRANSPORT=streamable-http \
    GDEX_MCP_HOST=0.0.0.0 \
    GDEX_MCP_PORT=8080

# GDEX_BASE_URL and (for local/single-user runs only) GDEX_TOKEN are read
# from the environment at startup — set via the Helm chart's values.yaml,
# not baked into the image.
CMD ["gdex-mcp"]
