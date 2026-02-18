# Add Pause Reason

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add a pause reason feature so when a check is paused, an optional reason can be stored (e.g. "Holiday maintenance"). When the check is resumed, clear the reason. Expose the reason in the check's API response.

## 1. `Check` model (`/app/hc/api/models.py`)

Add a new field to the existing `Check` model:

| Field | Type | Details |
|-------|------|---------|
| `pause_reason` | `CharField` | `max_length=200, blank=True, default=""` |

## 2. `Check.to_dict()` (`/app/hc/api/models.py`)

Add `"pause_reason": self.pause_reason` to the dict returned by `Check.to_dict()` (always include it; it will be an empty string when not paused or when no reason was set).

## 3. Pause endpoint (`/app/hc/api/views.py`)

Extend the existing `pause` view (POST /api/v3/checks/<uuid:code>/pause):

- Accept an optional JSON body with a key `reason` (string, max 200 characters).
- If `reason` is provided: validate it is a string (return `400` with `{"error": "reason must be a string"}` if not). Validate length ≤ 200 (return `400` with `{"error": "reason too long"}` if longer). Set `check.pause_reason = reason` before saving.
- If `reason` is not provided or is empty, set `check.pause_reason = ""`.
- Existing behavior (status change, flip, etc.) unchanged.

## 4. Resume endpoint (`/app/hc/api/views.py`)

Extend the existing `resume` view (POST /api/v3/checks/<uuid:code>/resume):

- Before saving the check, set `check.pause_reason = ""` so the reason is cleared when the check is resumed.

## 5. Migration

Generate with `python manage.py makemigrations api --name pausereason`.

## Constraints

- Don't modify existing tests
- Follow existing patterns for error responses
