# Dev/local image — same base strategy as Dockerfile.prod (native arch).
FROM python:3.12-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ffmpeg \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .
RUN mkdir -p /app/data

EXPOSE 7860

CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
