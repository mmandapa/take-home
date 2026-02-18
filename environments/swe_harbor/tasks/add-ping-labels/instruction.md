# Add Ping Labels

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add a ping labels feature so checks can have named labels (e.g. "deploy", "health") and each ping can optionally be tagged with one of those labels. Expose POST/GET endpoints for labels and include the label name in each ping when listing pings.

## 1. `PingLabel` model (`/app/hc/api/models.py`)

New model with these fields:

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="ping_labels"` |
| `name` | `CharField` | `max_length=100` |

Unique constraint: `(owner, name)` — one label name per check.

Add `to_dict()` returning: `uuid`, `name`.

`Meta` class: `ordering = ["name"]`.

## 2. Extend `Ping` model (`/app/hc/api/models.py`)

Add an optional FK to `PingLabel`:

| Field | Type | Details |
|-------|------|---------|
| `label` | `ForeignKey` to `PingLabel` | `null=True, blank=True, on_delete=models.SET_NULL, related_name="pings"` |

In `Ping.to_dict()`, add `"label": self.label.name if self.label else None`.

## 3. Ping creation with label

When a ping is created (existing ping endpoint), accept an optional query parameter `label` (label name). If the check has a label with that name, set the new ping's `label` to that `PingLabel`; otherwise leave the ping's label unset. No error if the label name is missing or doesn't exist — just ignore.

- Update the view that handles ping requests to read `request.GET.get("label")` and resolve the label by name for the check; pass it into the check's `ping()` method.
- Update `Check.ping()` to accept an optional keyword argument `label: PingLabel | None = None` and set `ping.label = label` before saving the ping.

## 4. API endpoints for labels (`/app/hc/api/views.py`)

### `POST /api/v3/checks/<uuid:code>/labels/`

Create a label for the check.

- Use `@authorize` (write key required)
- JSON body: `name` (required string, max 100)
- Validate that `name` is present and non-empty (return `400` with `{"error": "name is required"}` if missing or empty)
- Validate length ≤ 100 (return `400` with `{"error": "name too long"}` if longer)
- Unique per check: if a label with that name already exists for this check, return `409` with `{"error": "label already exists"}`
- Return the label JSON with status `201`
- `403` if wrong project, `404` if check doesn't exist

### `GET /api/v3/checks/<uuid:code>/labels/`

List labels for the check.

- Use `@authorize_read`
- Returns `{"labels": [...]}`, sorted by name
- `403` if wrong project, `404` if check doesn't exist

Wire these with a dispatcher `check_labels` (GET → list, POST → create). Decorate with `@csrf_exempt` and `@cors("GET", "POST")`.

## 5. URL routes (`/app/hc/api/urls.py`)

Add to the `api_urls` list:

```
path("checks/<uuid:code>/labels/", views.check_labels, name="hc-api-labels"),
```

## 6. Migration

Generate with `python manage.py makemigrations api --name pinglabel`.

## Constraints

- Don't modify existing tests
- Follow existing patterns for decorators, error responses, and URL routing
