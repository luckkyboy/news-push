# Oil Adjustment Calendar Design

## Context

The oil price push currently polls the Sichuan Development and Reform Commission listing every day during the evening window. That is wasteful because the underlying domestic refined oil price mechanism only adjusts on a 10-working-day cycle.

## Decision

Use a repository-managed static JSON calendar for 2026 refined oil adjustment dates. The application will check whether the current day is an adjustment day before fetching the Sichuan listing page.

This avoids runtime dependence on third-party schedule pages while still using stable public rules and public holiday data to produce the calendar.

## Sources

- National Development and Reform Commission pricing mechanism rules:
  - `https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=19805`
- 2026 holiday/workday data used to derive workday boundaries:
  - `https://raw.githubusercontent.com/bastengao/chinese-holidays-data/master/data/2026.json`

## Architecture

Add a small calendar loader in the oil domain that reads packaged JSON data and exposes `is_adjustment_day(date) -> bool`.

`OilPriceJob.run()` will perform checks in this order:

1. `already_sent`
2. `not_adjustment_day`
3. existing listing / attachment / parsing flow

## Data Shape

Store one JSON file in package data with:

- calendar metadata
- source URLs
- yearly adjustment date lists

The initial file only needs 2026 entries plus the previous anchor date used during derivation.

## Error Handling

If the calendar does not contain a year, treat the day as unsupported and skip with `not_adjustment_day`. This is safer than scraping daily without an explicit schedule.

## Testing

Add tests for:

- calendar membership on known 2026 dates
- oil job skipping on non-adjustment days without touching the source
- oil job continuing on adjustment days

