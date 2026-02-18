# Add Check Priority

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add a **priority** to checks so that each check has a priority level (low / normal / high) that affects list ordering and is readable and writable via the API. There is no new resource — extend the existing Check model, API Spec, and list/detail endpoints.

### Allowed values and default

- **Priority values:** Integer `0` = low, `1` = normal, `2` = high.
- **Default:** `1` (normal). Existing checks and any create/update that omits `priority` must get default 1.

### Behavior

1. **Model** (`/app/hc/api/models.py`)
   - Add a field (e.g. `priority`) on `Check`: integer, default `1`, allowed values 0–2 (you may use a small IntegerField or PositiveSmallIntegerField).
   - Include `priority` in the dict returned by `Check.to_dict()` so GET single check and GET list checks expose it.
   - Update `CheckDict` (or the TypedDict used by `to_dict`) to include `priority`.

2. **Create/update** (`/app/hc/api/views.py`)
   - The request body Spec (or equivalent) used for create_check and update_check must accept an optional `priority` field.
   - Validate that when provided, `priority` is 0, 1, or 2 (e.g. Pydantic `ge=0, le=2` or equivalent). Return 400 for invalid values.
   - In `_update()`, when `priority` is provided in the spec, set `check.priority` so that create and update persist it. When omitted, leave the existing value (or default for new checks).

3. **List ordering**
   - GET `/api/v1/checks/`, `/api/v2/checks/`, and `/api/v3/checks/` must return checks ordered by **priority descending** (high first), then by **name** (or existing secondary sort). So the queryset in `get_checks()` should use an ordering such as `order_by("-priority", "name")` (or equivalent).

4. **Migration**
   - Create and apply a migration for the new field: e.g. `python manage.py makemigrations api --name check_priority` and `python manage.py migrate`.

### Files to modify

- `/app/hc/api/models.py` — Check model (new field, default), CheckDict, and `to_dict()`.
- `/app/hc/api/views.py` — Spec (optional `priority` with validation), `_update()` (set `check.priority` when provided), `get_checks()` (ordering by priority then name).
- New migration under `hc/api/migrations/` (via `makemigrations`).

### Constraints

- Do not change behavior of other tasks or existing tests; follow existing patterns in the codebase.
- Project scoping and auth for checks are unchanged: only the current project’s checks are listed/updated, and API key rules remain the same.
