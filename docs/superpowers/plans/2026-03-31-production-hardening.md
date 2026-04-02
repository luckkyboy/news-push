# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve reliability and observability of outbound push jobs without changing the product scope.

**Architecture:** Keep the existing FastAPI app and job classes intact, but add a small reusable retry helper, targeted logging in the job and webhook flow, and API tests that lock the current behavior. Avoid broad refactors so this can ship as a focused hardening pass.

**Tech Stack:** Python 3.12, FastAPI, APScheduler, httpx, pytest

---

### Task 1: Lock Retry Requirements with Tests

**Files:**
- Modify: `tests/test_news_image_service.py`
- Modify: `tests/test_oil_service.py`
- Modify: `tests/test_wecom.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fetch_if_exists_retries_after_transient_request_error() -> None: ...
def test_parse_docx_prices_retries_after_transient_request_error() -> None: ...
def test_send_text_retries_after_transient_request_error() -> None: ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_news_image_service.py tests/test_oil_service.py tests/test_wecom.py -p no:cacheprovider`
Expected: FAIL because the current implementation performs a single request with no retry handling.

- [ ] **Step 3: Write minimal implementation**

```python
def get_with_retry(...): ...
def post_with_retry(...): ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_news_image_service.py tests/test_oil_service.py tests/test_wecom.py -p no:cacheprovider`
Expected: PASS

### Task 2: Add Job and Delivery Logging

**Files:**
- Modify: `src/news_push/news_image.py`
- Modify: `src/news_push/oil.py`
- Modify: `src/news_push/wecom.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_run_logs_skip_reason_when_image_missing(caplog) -> None: ...
def test_oil_job_logs_skip_reason_when_listing_missing(caplog) -> None: ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_news_image_service.py tests/test_oil_service.py -p no:cacheprovider`
Expected: FAIL because the current jobs do not emit those log lines.

- [ ] **Step 3: Write minimal implementation**

```python
logger.info("news image skipped", extra={...})
logger.info("oil price skipped", extra={...})
logger.info("wecom message delivered", extra={...})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_news_image_service.py tests/test_oil_service.py -p no:cacheprovider`
Expected: PASS

### Task 3: Add FastAPI Endpoint Coverage

**Files:**
- Modify: `tests/test_app.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing tests**

```python
def test_status_reports_jobs_and_webhook_state() -> None: ...
def test_manual_job_run_returns_missing_webhook_when_not_configured() -> None: ...
def test_manual_job_run_returns_job_result_when_configured() -> None: ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_app.py -p no:cacheprovider`
Expected: FAIL because the app endpoints are not currently covered and `fastapi[testclient]` style support is not declared.

- [ ] **Step 3: Write minimal implementation**

```python
dev = [
  "pytest>=8.0.0,<9.0.0",
  "httpx>=0.27.0,<1.0.0",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_app.py -p no:cacheprovider`
Expected: PASS

### Task 4: Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update docs if behavior or verification guidance changed**

```markdown
Mention retry-and-log hardening only if the user-facing behavior or troubleshooting guidance changed.
```

- [ ] **Step 2: Run targeted verification**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q tests/test_app.py tests/test_news_image_service.py tests/test_oil_service.py tests/test_wecom.py -p no:cacheprovider`
Expected: PASS

- [ ] **Step 3: Run full verification**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run --project . --extra dev python -m pytest -q -p no:cacheprovider`
Expected: PASS with zero failures
