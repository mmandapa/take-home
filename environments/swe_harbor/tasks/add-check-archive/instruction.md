# Add Check Archival and Restore

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add the ability to archive a check (hide it from the default list and reject pings with **410 Gone**) and to restore it later (with a capacity check). Record each archive and restore in an `ArchiveLog`. Change existing behavior: **GET checks** should exclude archived checks by default and support `?archived=1` to list only archived checks; the **ping endpoint** (by UUID and by slug) must return **410 Gone** when the check is archived, without calling `check.ping()`.

## 1. Model changes (`/app/hc/api/models.py`)

### New model: `ArchiveLog`

Add after the `Flip` model (or after any existing log model).

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="archive_logs"` (do not name the field `check` — it clashes with Django's `Model.check()`) |
| `action` | `CharField` | `max_length=20` — `"archived"` or `"restored"` |
| `at` | `DateTimeField` | `default=now` |
| `by` | `CharField` | `max_length=200, blank=True` |

- `to_dict()`: `uuid`, `check` (str of the Check's code), `action`, `at` (isostring), `by`.
- `Meta`: `ordering = ["-at"]`.

### Check model change

- Add `archived_at` — `DateTimeField(null=True, blank=True)`. When non-null, the check is considered "archived".

## 2. Migration

Generate with `python manage.py makemigrations api --name check_archived_archivelog`, then apply with `python manage.py migrate`.

## 3. API endpoints (`/app/hc/api/views.py`)

### Changes to existing behavior

**GET /api/v1/checks/, /api/v2/checks/, /api/v3/checks/** (`get_checks`)

- By default **exclude** checks where `archived_at` is not null (only show non-archived).
- Query param `archived=1` or `archived=true`: return **only** checks where `archived_at` is not null (archived-only list).

**Ping endpoint** (`ping` and `ping_by_slug`)

- After resolving the check (by code or by slug), if `check.archived_at` is set: return **410 Gone** (e.g. `HttpResponse(status=410)`). Do **not** call `check.ping()` in that case.

### New endpoints

**POST /api/v3/checks/<uuid:code>/archive/**

- Decorators: `@cors("POST")`, `@csrf_exempt`, `@authorize`.
- Body: optional JSON with `"reason"` or empty; store in `ArchiveLog.by` or leave blank.
- If check is already archived (`archived_at` set): 400 `{"error": "check already archived"}`.
- Else: set `check.archived_at = timezone.now()`, save check, create `ArchiveLog(owner=check, action="archived", by=...)`. Return 200 and the check's `to_dict(v=request.v)`.

**POST /api/v3/checks/<uuid:code>/restore/**

- Same decorators.
- If check is not archived: 400 `{"error": "check is not archived"}`.
- If `request.project.num_checks_available() <= 0`: 400 `{"error": "project has no checks available"}` (restore consumes a slot).
- Else: set `check.archived_at = None`, reset check state (e.g. `status="new"`, clear `last_ping`, `alert_after`, `last_start`, `last_duration`, `n_pings=0` — same idea as transfer reset), save; create `ArchiveLog(owner=check, action="restored", ...)`. Return 200 and the check's `to_dict(v=request.v)`.

**GET /api/v3/checks/<uuid:code>/archive-history/** (optional)

- `@authorize_read`. Return `{"archive_history": [...]}` — list of `ArchiveLog` entries for this check (filter by owner). 403/404 as usual.

## 4. URL routes (`/app/hc/api/urls.py`)

Add to `api_urls`:

```python
path("checks/<uuid:code>/archive/", views.check_archive, name="hc-api-archive"),
path("checks/<uuid:code>/restore/", views.check_restore, name="hc-api-restore"),
path("checks/<uuid:code>/archive-history/", views.check_archive_history, name="hc-api-archive-history"),
```

(You may omit `archive-history` if you document it as optional and do not add a route for it; if you add the route, implement the view.)

## Constraints

- Don't modify existing tests.
- Follow existing patterns for decorators and error responses.
- Archive and restore must be consistent: archived checks must not accept pings (410) and must be excluded from the default checks list.
