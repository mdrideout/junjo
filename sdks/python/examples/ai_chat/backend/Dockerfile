FROM python:3.13-slim-trixie

LABEL org.opencontainers.image.source="https://github.com/mdrideout/junjo" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/

ENV PATH="/workspace/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY examples/base/pyproject.toml examples/base/README.md ./examples/base/
COPY examples/getting_started/pyproject.toml examples/getting_started/README.md ./examples/getting_started/
COPY examples/ai_chat/backend ./examples/ai_chat/backend

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package junjo-ai-chat-example --no-dev

EXPOSE 26252

CMD ["fastapi", "dev", "--entrypoint", "ai_chat.main:app", "--host", "0.0.0.0", "--port", "26252"]
