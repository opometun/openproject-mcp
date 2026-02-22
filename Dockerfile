FROM python:3.11.9-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.txt README.md ./
# If uv.lock exists in the repo, uncomment the next line to leverage locked deps
# COPY uv.lock ./
# Bring in source for build
COPY src ./src
RUN pip install --no-cache-dir build hatchling
RUN python -m build --wheel --no-isolation

FROM python:3.11.9-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FASTMCP_HOST=0.0.0.0 FASTMCP_PORT=8000
RUN useradd -m app && chown -R app /app
COPY --from=builder /app/dist /tmp/dist
# Install wheel with the http extra so uvicorn/starlette are present at runtime
RUN WHEEL=$(ls /tmp/dist/*.whl) \
    && pip install --no-cache-dir "${WHEEL}[http]" \
    && rm -rf /tmp/dist
USER app
EXPOSE 8000
CMD ["python", "-m", "openproject_mcp.transports.http.main"]
