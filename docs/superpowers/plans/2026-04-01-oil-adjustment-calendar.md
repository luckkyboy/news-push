# Oil Adjustment Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip the oil price fetch flow on dates that are not domestic refined oil adjustment days.

**Architecture:** Package a static 2026 adjustment-day JSON file, add a thin loader in the oil domain, and gate `OilPriceJob.run()` before any remote fetch. Keep the existing scrape and send flow unchanged for valid adjustment days.

**Tech Stack:** Python 3.12, FastAPI, APScheduler, pytest, importlib.resources

---

### Task 1: Calendar Tests First

**Files:**
- Modify: `tests/test_oil_service.py`

- [ ] **Step 1: Write failing tests for calendar membership and non-adjustment skip**

```python
def test_adjustment_calendar_recognizes_known_2026_dates() -> None:
    calendar = OilAdjustmentCalendar()
    assert calendar.is_adjustment_day(date(2026, 1, 6)) is True
    assert calendar.is_adjustment_day(date(2026, 1, 7)) is False

def test_oil_job_skips_when_today_is_not_adjustment_day() -> None:
    ...
    assert result.reason == "not_adjustment_day"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_oil_service.py -q`
Expected: FAIL because `OilAdjustmentCalendar` and `not_adjustment_day` behavior do not exist yet.

### Task 2: Minimal Calendar Implementation

**Files:**
- Create: `src/news_push/data/oil_adjustment_calendar.json`
- Modify: `src/news_push/oil.py`
- Modify: `pyproject.toml`
- Test: `tests/test_oil_service.py`

- [ ] **Step 1: Add packaged JSON calendar data**

```json
{
  "calendar_name": "cn_refined_oil_adjustment_days",
  "years": {
    "2026": {
      "adjustment_dates": ["2026-01-06", "2026-01-20"]
    }
  }
}
```

- [ ] **Step 2: Add minimal loader and job gate**

```python
class OilAdjustmentCalendar:
    def is_adjustment_day(self, target_day: date) -> bool:
        ...

if not self.calendar.is_adjustment_day(target_day):
    return JobResult(sent=False, reason="not_adjustment_day")
```

- [ ] **Step 3: Package the JSON file**

```toml
[tool.setuptools.package-data]
news_push = ["data/*.json"]
```

- [ ] **Step 4: Run the focused test file**

Run: `pytest tests/test_oil_service.py -q`
Expected: PASS

### Task 3: Broader Verification and Docs

**Files:**
- Modify: `README.md`
- Test: `tests/test_app.py`

- [ ] **Step 1: Document the new gating rule**

```markdown
- 只有命中调价窗口日才会抓取四川发改委公告
```

- [ ] **Step 2: Run relevant test suite**

Run: `pytest tests/test_oil_service.py tests/test_app.py -q`
Expected: PASS
