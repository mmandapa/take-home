# Fix Check Tag Filtering and API Version Bugs

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## Intended behavior

**GET /api/v1/checks/, /api/v2/checks/, /api/v3/checks/** (list checks):

- Supports an optional `tag` query parameter. Multiple tags can be passed (e.g. `?tag=foo&tag=bar`). Only checks whose **space-separated** tags contain **all** requested tags are returned (AND semantics). Tag matching must be exact per tag token — e.g. requesting tag `up` must not match a check whose tags string contains `startup` as a substring.
- Response shape depends on the API version in the path: v1, v2, and v3 each return the appropriate structure (e.g. v3 includes `uuid`, v1 may differ). The version is determined by the request path (`/api/v1/`, `/api/v2/`, `/api/v3/`).
- Project scoping is unchanged: only checks for the project identified by the API key are returned. 401 for bad or missing API key.

## What’s wrong

The codebase currently has **bugs** that cause:

1. **Tag filtering:** Incorrect behavior when filtering by tag (e.g. wrong tag parsing, or returning checks that do not actually have all requested tags, or substring false positives).
2. **API version:** v2 and v3 list endpoints may return the wrong response shape (e.g. v1-style when requesting v3).

Your task is to **find and fix** these bugs so that the behavior matches the intended behavior above. Do not add new features; only fix the broken behavior.

## Constraints

- Don't modify existing tests in other tasks.
- Follow existing patterns in the codebase.
