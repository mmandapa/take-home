# Add Activity Log

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add an activity log that records when checks are created, updated, paused, or resumed. There is **no** "create activity" API — activity records are created **inside existing API views** when those actions succeed. The only new endpoint is **GET** to list activity for the current project. Read-only API key is allowed for the list endpoint.

## 1. `ActivityLog` model (`/app/hc/api/models.py`)

New model with these fields:

| Field | Type | Details |
|-------|------|---------|
| `project` | `ForeignKey` to `Project` | `on_delete=models.CASCADE`, `related_name="activity_logs"` (import `Project` from `hc.accounts.models`) |
| `action` | `CharField` | `max_length=50` (one of: `check_created`, `check_updated`, `check_paused`, `check_resumed`) |
| `check_code` | `UUIDField` | `null=True`, `blank=True` — the check involved, if any |
| `details` | `CharField` | `max_length=500`, `blank=True`, `default=""` |
| `created` | `DateTimeField` | `default=now` |

**Meta:** `ordering = ["-created"]`.

**to_dict():** returns `action`, `check_code` (str(uuid) if set, else `None`), `details`, `created` (ISO 8601, no microseconds; use existing `isostring()` in this file).

Optional: a class method `ActivityLog.log(project, action, check_code=None, details="")` that creates and saves a record (so views can call one line per injection).

## 2. Logging injection (views only on success)

In `/app/hc/api/views.py`, **after** the main work and **before** the successful `return`, create an activity record for:

- **create_check** — When a check is successfully created or updated (before `return JsonResponse(...)`). Log with `action="check_created"` if the check was just created, else `action="check_updated"`. Pass the check's `code` and optionally `details` (e.g. check name).
- **update_check** — When a check is successfully updated (before return). Log with `action="check_updated"`, the check's `code`, and optional details.
- **pause** — When a check is successfully paused (before return). Log with `action="check_paused"`, the check's `code`, and optional details.
- **resume** — When a check is successfully resumed (before return). Log with `action="check_resumed"`, the check's `code`, and optional details.

Do **not** log on validation error or 403/404 — only when the view is about to return a successful response.

## 3. List activity endpoint (`/app/hc/api/views.py`)

**GET /api/v3/activity/**

- Use `@authorize_read` (read-only API key **is** allowed; this is the only endpoint that must allow read-only key for GET).
- Return `{"activity": [...]}` — all ActivityLog rows for `request.project`, newest first (use model default ordering).
- 401 for bad or missing API key.
- Decorate with `@csrf_exempt` and `@cors("GET")` so OPTIONS works. Add to `api_urls` so the path works under v1, v2, and v3.

## 4. URL route (`/app/hc/api/urls.py`)

Add to the `api_urls` list:

```
path("activity/", views.list_activity, name="hc-api-activity"),
```

(Full path is `/api/v3/activity/` when using v3; project is inferred from API key.)

## 5. Migration

Generate with `python manage.py makemigrations api --name activitylog`.

## Constraints

- Don't modify existing tests in other tasks.
- Use `isostring()` for datetime formatting (already in the codebase).
- Follow existing patterns for decorators and URL routing.
