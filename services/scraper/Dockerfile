FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libxshmfence1 \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/scraper/pyproject.toml ./services/scraper/pyproject.toml
COPY services/scraper/src ./services/scraper/src

RUN uv sync --frozen --no-dev \
  --package news_scraper \
  --package news_db --package news_schemas --package news_config --package news_observability

COPY rss-mcp/dist ./rss-mcp/dist
COPY rss-mcp/package.json ./rss-mcp/package.json
RUN cd rss-mcp && npm install --production

RUN npx -y @playwright/mcp@latest --help >/dev/null 2>&1 || true
RUN npx -y playwright install chromium --with-deps

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    RSS_MCP_PATH=/app/rss-mcp/dist/index.js \
    NODE_ENV=production

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "news_scraper.main:app", "--host", "0.0.0.0", "--port", "8000"]
