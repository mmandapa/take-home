# Add Check Maintenance Windows

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add a maintenance window feature to the REST API so users can schedule periods when a check is in maintenance (e.g. "server upgrade 2pm–4pm"). The API exposes create and list endpoints, and the check's dict includes a count of maintenance windows.

## 1. `MaintenanceWindow` model (`/app/hc/api/models.py`)

New model with these fields:

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="maintenance_windows"` |
| `start` | `DateTimeField` | required (no default) |
| `end` | `DateTimeField` | `null=True, blank=True` — optional end time |
| `reason` | `CharField` | `max_length=200, blank=True, default=""` |

Add `to_dict()` returning: `uuid`, `start` (ISO 8601, no microseconds), `end` (ISO 8601, no microseconds, or `None` if null), `reason`.

Use the existing `isostring()` helper in this file for datetime formatting.

`Meta` class: `ordering = ["-start"]`.

## 2. Migration (`/app/hc/api/migrations/`)

Generate with `python manage.py makemigrations api --name maintenancewindow`.

## 3. API endpoints (`/app/hc/api/views.py`)

### `POST /api/v3/checks/<uuid:code>/maintenance/`

Create a maintenance window.

- Use `@authorize` (write key required)
- JSON body: `start` (required, ISO 8601 datetime string), `end` (optional, ISO 8601 datetime string), `reason` (optional string, max 200)
- Validate that `start` is present and a valid ISO 8601 datetime (return `400` with `{"error": "invalid start"}` if missing or invalid)
- If `end` is provided, validate it is a valid ISO 8601 datetime; if invalid return `400` with `{"error": "invalid end"}`
- If both `start` and `end` are provided, validate `end >= start`; otherwise return `400` with `{"error": "end must be after start"}`
- Validate `reason` is a string if provided; if not a string return `400` with `{"error": "reason must be a string"}`. If provided and longer than 200 chars return `400` with `{"error": "reason too long"}`
- Return the maintenance window JSON with status `201`
- `403` if check is in a different project
- `404` if check doesn't exist

### `GET /api/v3/checks/<uuid:code>/maintenance/`

List maintenance windows for a check.

- Use `@authorize_read`
- Returns `{"maintenance_windows": [...]}`, newest first (by `start`)
- `403` if wrong project, `404` if check doesn't exist

Wire these up with a dispatcher called `check_maintenance` that sends GET to the list handler and POST to the create handler. Decorate with `@csrf_exempt` and `@cors("GET", "POST")`.

## 4. URL routes (`/app/hc/api/urls.py`)

Add to the `api_urls` list (works across v1/v2/v3 automatically):

```
path("checks/<uuid:code>/maintenance/", views.check_maintenance, name="hc-api-maintenance"),
```

## 5. `Check.to_dict()` (`/app/hc/api/models.py`)

Add `"maintenance_windows_count"` (integer) to the dict returned by `Check.to_dict()`.

## Constraints

- Don't modify existing tests
- Use `isostring()` for datetime formatting (already in the codebase)
- Follow existing patterns for decorators, error responses, and URL routing (see annotations/transfer examples)
