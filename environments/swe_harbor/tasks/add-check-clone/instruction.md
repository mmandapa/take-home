# Add Check Clone API

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add an API to clone an existing check into the same project or another project. The new check gets a new UUID and copied configuration (name, slug, tags, timeout, grace, schedule, etc.); pings and flips are not copied. Record each clone in a `CloneLog`. When cloning to another project, require the target project's write API key (`target_api_key`), same pattern as the transfer API. Extend `Check.to_dict()` with `cloned_from` (source check code when this check was created by cloning, else `null`).

## 1. Model changes (`/app/hc/api/models.py`)

### New model: `CloneLog`

Add after the `Flip` model.

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `source_check` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="clone_operations_as_source"` |
| `cloned_check` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="clone_operations_as_clone"` |
| `target_project` | `ForeignKey` to `Project` | `on_delete=models.SET_NULL, null=True` (use `"accounts.Project"`), `related_name="+"` optional |
| `created` | `DateTimeField` | `default=now` |
| `cloned_by` | `CharField` | `max_length=200, blank=True` |

- `to_dict()` returning: `uuid`, `source_check` (str code), `cloned_check` (str code), `target_project` (str code or None), `created` (isostring), `cloned_by`.
- `Meta`: `ordering = ["-created"]`.

### New method: `Check.clone(target_project, name_override=None, cloned_by="")`

All inside `transaction.atomic()` with `select_for_update()` on the source check (same pattern as `ping()` and `lock_and_delete()`).

1. **Validate capacity** — `target_project.num_checks_available() <= 0` → raise `ValueError("target project has no checks available")`.
2. **Create new Check** — Copy from self: name (or name_override), slug, tags, desc, kind, timeout, grace, schedule, tz, filter_subject, filter_body, start_kw, success_kw, failure_kw, methods, manual_resume. Set `project=target_project`. Do **not** copy: n_pings, last_ping, status, alert_after, last_start, last_duration, etc. (use model defaults).
3. **Assign channels** — `new_check.channel_set.set(Channel.objects.filter(project=target_project))` (same idea as transfer: new check gets target project's channels).
4. **Create CloneLog** — source_check=self, cloned_check=new_check, target_project=target_project, cloned_by=cloned_by.
5. **Save and return** — new_check.save(), return new_check.

### `Check.to_dict()` extension

Add `"cloned_from": str | None` — if this check is the `cloned_check` in any CloneLog, set to the source check's code (string); else `None`. One extra query per check is acceptable.

## 2. Migration

Generate with `python manage.py makemigrations api --name clonelog`, then apply with `python manage.py migrate`.

## 3. API endpoints (`/app/hc/api/views.py`)

### POST /api/v3/checks/<uuid:code>/clone/

- Decorators: `@cors("POST")`, `@csrf_exempt`, `@authorize`.
- JSON body: `project` (optional) — UUID of target project; if omitted, clone to same project. `name` (optional) — override name for the new check. `target_api_key` (required when `project` is different) — write API key for the target project.
- Auth: request API key identifies the source project. If target project != source project, require `target_api_key` and validate it matches the target project's `api_key`; else 403 `{"error": "not authorized for target project"}`.
- Validation: 404 if check not found or check belongs to another project; 400 if invalid project UUID; 404 if target project does not exist; 400 if target has no capacity; 400 if cloning to same project but `target_api_key` provided (e.g. `{"error": "cannot clone to same project"}` or omit target_api_key for same project).
- On success: 201 and body = cloned check's `to_dict(v=request.v)`.

### GET /api/v3/checks/<uuid:code>/clones/

- Decorators: `@cors("GET")`, `@csrf_exempt`, `@authorize_read`.
- Returns `{"clones": [...]}` — list of CloneLog entries where `source_check` equals the check (i.e. clones created from this check). 403 if check belongs to another project; 404 if check does not exist.

## 4. URL routes (`/app/hc/api/urls.py`)

Add to the `api_urls` list (same pattern as other check sub-resources):

```python
path("checks/<uuid:code>/clone/", views.check_clone, name="hc-api-clone"),
path("checks/<uuid:code>/clones/", views.check_clones, name="hc-api-clones"),
```

## Constraints

- Don't modify existing tests.
- Follow existing patterns for decorators, error responses, and JSON bodies.
- Clone must be atomic: if any step fails, nothing gets committed.
