# SECFEDCLAW — container image. Two targets from one file:
#
#   runtime             (DEFAULT, slim ~200MB) — scan / scoring / EDGAR / dashboard /
#                       serve. Web/social SEARCH runs via Firecrawl or AWS Bedrock,
#                       or degrades to replay. No in-container Chromium.
#   runtime-playwright  (~1.8GB) — adds scrapegraphai + Chromium for in-container
#                       live X/social scraping.
#
# Build:
#   docker build --target runtime            -t secfedclaw:slim .
#   docker build --target runtime-playwright -t secfedclaw:full .
#
# Secrets are NEVER baked in — pass them at run time (--env-file .env, -e KEY=…,
# Docker secrets, ECS task env, or a Bedrock instance role). Persistent data
# (out/ state/ logs/ live_cache/ flatfiles/) must be mounted as volumes; see
# docker-compose.yml and README §14.

# Base tag for the playwright target. Declared global (before any FROM) so it's
# usable in the FROM below; pin it to the Playwright version `pip install
# scrapegraphai` pulls. Unused by the default `runtime` target.
ARG PW_TAG=v1.49.0-jammy

# =========================================================================
# runtime (default, slim)
# =========================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Non-root: design for tired humans at 3am, not root in a container.
RUN useradd --create-home --uid 10001 secfedclaw
WORKDIR /app

# Only numpy is required at runtime (model/usage/dashboard). scan/scoring/serve
# are stdlib. scrapegraphai/boto3/langchain are imported lazily, so the slim
# image runs everything except in-container Chromium search.
RUN pip install --no-cache-dir "numpy>=1.24"

COPY . .
RUN chown -R secfedclaw:secfedclaw /app
USER secfedclaw

EXPOSE 8787
# 302 (redirect), 200, or 401 (token gate) all mean "server is up". Use
# http.client, NOT urllib.urlopen — urlopen raises on 401, which would falsely
# mark a token-protected (healthy) server unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',8787,timeout=4); c.request('GET','/'); sys.exit(0 if c.getresponse().status in (200,302,401) else 1)" \
  || exit 1

# Default command: the dashboard web service. Binds 0.0.0.0 (the container's own
# interface) so it's reachable via a published port; serve.py then REQUIRES an
# access token by default (printed at startup). Publish to host loopback only.
# Batch runs override the command, e.g. `docker run … python daily.py`.
CMD ["python", "serve.py", "--host", "0.0.0.0", "--port", "8787"]

# =========================================================================
# runtime-playwright (in-container live scraping)
# =========================================================================
# PW_TAG is the global ARG declared at the top — pin it to match the Playwright
# version `pip install scrapegraphai` pulls (mismatched Chromium ↔ Playwright
# fails at run time). Tags: https://mcr.microsoft.com/v2/playwright/python/tags/list
FROM mcr.microsoft.com/playwright/python:${PW_TAG} AS runtime-playwright

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# scrapegraphai + a Gemini LLM binding for the search() path; Chromium + system
# libs are already in the base image. Add boto3 + langchain-aws here too if you
# run the search/explainer LLM on AWS Bedrock.
RUN pip install --no-cache-dir numpy scrapegraphai langchain-google-genai

COPY . .
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',8787,timeout=4); c.request('GET','/'); sys.exit(0 if c.getresponse().status in (200,302,401) else 1)" \
  || exit 1
CMD ["python", "serve.py", "--host", "0.0.0.0", "--port", "8787"]
