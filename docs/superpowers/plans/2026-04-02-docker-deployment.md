# Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the minimum Docker deployment assets so `news-push` can be built and run on a self-hosted server with `docker compose` and persisted state.

**Architecture:** Build a single-container image from `python:3.12-slim`, run the existing `python -m news_push` entrypoint, and use `docker-compose.yml` to provide environment variables, port mapping, restart policy, health check, and a host-mounted state directory. Keep the application code unchanged and document the deployment flow in the README.

**Tech Stack:** Docker, Docker Compose, Python 3.12, FastAPI, Uvicorn

---

### Task 1: Add Container Build Assets

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `.gitignore`

- [ ] **Step 1: Create the image build definition**

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["python", "-m", "news_push"]
```

- [ ] **Step 2: Ignore local-only Docker build context files**

```gitignore
.git
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.tox/
__pycache__/
*.pyc
*.pyo
*.pyd
*.egg-info/
build/
dist/
.env
.env.local
.codex/
.idea/
.vscode/
docs/
tests/
```

- [ ] **Step 3: Keep Git from tracking local deployment secrets**

Add compose env helper files to `.gitignore` if they are not already covered:

```gitignore
.env
.env.local
```

- [ ] **Step 4: Verify the new files exist**

Run: `ls Dockerfile .dockerignore`
Expected: both files are listed

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore .gitignore
git commit -m "chore: add docker build assets"
```

### Task 2: Add Compose Deployment Definition

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create the compose file**

```yaml
services:
  news-push:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: news-push
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      WECOM_WEBHOOK_URL: ${WECOM_WEBHOOK_URL}
      NEWS_IMAGE_BASE_URL: ${NEWS_IMAGE_BASE_URL:-https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images}
      STATE_FILE: /data/state.json
      TZ: ${TZ:-Asia/Shanghai}
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

- [ ] **Step 2: Validate the compose syntax**

Run: `docker compose config`
Expected: rendered compose output without syntax errors

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docker compose deployment"
```

### Task 3: Document Docker Deployment

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Docker deployment section**

Document:

- how to create a `.env` file with `WECOM_WEBHOOK_URL`
- how to create the `data/` directory
- how to run `docker compose up -d --build`
- how to inspect logs with `docker compose logs -f`

- [ ] **Step 2: Add verification commands**

Document these exact checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/status
curl -X POST http://127.0.0.1:8000/jobs/news-image/run
curl -X POST http://127.0.0.1:8000/jobs/oil/run
```

- [ ] **Step 3: Add operational notes**

Document:

- `STATE_FILE` must be persisted through `./data:/data`
- `POST /jobs/oil/run` returns `not_adjustment_day` on non-window dates
- yearly oil calendar data must be refreshed before entering a new year

- [ ] **Step 4: Review the README diff for stale local-run instructions**

Run: `git diff -- README.md`
Expected: Docker instructions are added without removing valid existing local-run docs

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add docker deployment guide"
```

### Task 4: Verify Docker Deployment Assets

**Files:**
- Verify: `Dockerfile`
- Verify: `.dockerignore`
- Verify: `docker-compose.yml`
- Verify: `README.md`

- [ ] **Step 1: Build the image**

Run: `docker build -t news-push:test .`
Expected: build completes successfully

- [ ] **Step 2: Render the compose config**

Run: `docker compose config`
Expected: valid rendered config

- [ ] **Step 3: Smoke-test the containerized service**

Run:

```bash
mkdir -p data
WECOM_WEBHOOK_URL=https://example.com/webhook docker compose up -d --build
curl http://127.0.0.1:8000/health
docker compose down
```

Expected:

- compose starts successfully
- `/health` returns `{"status":"ok"}`
- `docker compose down` stops the service cleanly

- [ ] **Step 4: Commit any doc-only follow-up if verification requires it**

```bash
git add Dockerfile .dockerignore docker-compose.yml README.md
git commit -m "chore: polish docker deployment assets"
```

- [ ] **Step 5: Final status check**

Run: `git status --short`
Expected: no uncommitted changes
