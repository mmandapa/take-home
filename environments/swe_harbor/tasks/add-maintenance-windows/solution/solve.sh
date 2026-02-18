#!/bin/bash
set -e

###############################################################################
# 1. Add the MaintenanceWindow model to hc/api/models.py
###############################################################################

cat >> /app/hc/api/models.py << 'PYEOF'


class MaintenanceWindow(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="maintenance_windows")
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-start"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "start": isostring(self.start),
            "end": isostring(self.end),
            "reason": self.reason,
        }
PYEOF

###############################################################################
# 2. Update Check.to_dict() — add maintenance_windows_count
###############################################################################

cd /app

python3 << 'PATCH1'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())
        elif self.kind in ("cron", "oncalendar"):
            result["schedule"] = self.schedule
            result["tz"] = self.tz

        return result'''

new = '''        result["maintenance_windows_count"] = self.maintenance_windows.count()

        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())
        elif self.kind in ("cron", "oncalendar"):
            result["schedule"] = self.schedule
            result["tz"] = self.tz

        return result'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. Add API views for maintenance windows
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@authorize_read
def list_maintenance_windows(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import MaintenanceWindow

    q = MaintenanceWindow.objects.filter(owner=check)
    return JsonResponse({"maintenance_windows": [w.to_dict() for w in q]})


@authorize
def create_maintenance_window(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import MaintenanceWindow

    start_str = request.json.get("start")
    if start_str is None or start_str == "":
        return JsonResponse({"error": "invalid start"}, status=400)
    if not isinstance(start_str, str):
        return JsonResponse({"error": "invalid start"}, status=400)
    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return JsonResponse({"error": "invalid start"}, status=400)

    end_str = request.json.get("end")
    end_dt = None
    if end_str is not None and end_str != "":
        if not isinstance(end_str, str):
            return JsonResponse({"error": "invalid end"}, status=400)
        try:
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return JsonResponse({"error": "invalid end"}, status=400)
        if end_dt < start_dt:
            return JsonResponse({"error": "end must be after start"}, status=400)

    reason = request.json.get("reason", "")
    if not isinstance(reason, str):
        return JsonResponse({"error": "reason must be a string"}, status=400)
    if len(reason) > 200:
        return JsonResponse({"error": "reason too long"}, status=400)

    window = MaintenanceWindow(
        owner=check,
        start=start_dt,
        end=end_dt,
        reason=reason,
    )
    window.save()

    return JsonResponse(window.to_dict(), status=201)


@csrf_exempt
@cors("GET", "POST")
def check_maintenance(request: HttpRequest, code: UUID) -> HttpResponse:
    if request.method == "POST":
        return create_maintenance_window(request, code)

    return list_maintenance_windows(request, code)
VIEWEOF

###############################################################################
# 4. Add URL routes
###############################################################################

python3 << 'PATCH2'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '''    path("channels/", views.channels),'''

new = '''    path(
        "checks/<uuid:code>/maintenance/",
        views.check_maintenance,
        name="hc-api-maintenance",
    ),
    path("channels/", views.channels),'''

content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 5. Create the migration
###############################################################################

cd /app
python manage.py makemigrations api --name maintenancewindow 2>&1
python manage.py migrate 2>&1
