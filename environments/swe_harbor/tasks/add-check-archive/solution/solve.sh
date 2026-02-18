#!/bin/bash
set -e
cd /app

###############################################################################
# 1. Add archived_at to Check and ArchiveLog model in hc/api/models.py
###############################################################################

python3 << 'PATCH0'
with open("/app/hc/api/models.py", "r") as f:
    content = f.read()

# Add archived_at to Check after status
old = '''    status = models.CharField(max_length=6, choices=STATUSES, default="new")

    class Meta:
        indexes = ['''

new = '''    status = models.CharField(max_length=6, choices=STATUSES, default="new")
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = ['''

content = content.replace(old, new, 1)

with open("/app/hc/api/models.py", "w") as f:
    f.write(content)
PATCH0

cat >> /app/hc/api/models.py << 'PYEOF'


class ArchiveLog(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="archive_logs")
    action = models.CharField(max_length=20)  # "archived" | "restored"
    at = models.DateTimeField(default=now)
    by = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-at"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "check": str(self.owner.code),
            "action": self.action,
            "at": isostring(self.at),
            "by": self.by,
        }
PYEOF

###############################################################################
# 2. get_checks: exclude archived by default; ?archived=1 for archived-only
###############################################################################

python3 << 'PATCH1'
with open("/app/hc/api/views.py", "r") as f:
    content = f.read()

old = '''@authorize_read
def get_checks(request: ApiRequest) -> JsonResponse:
    q = Check.objects.filter(project=request.project)
    if not request.readonly:'''

new = '''@authorize_read
def get_checks(request: ApiRequest) -> JsonResponse:
    q = Check.objects.filter(project=request.project)
    archived_param = request.GET.get("archived", "").strip().lower()
    if archived_param in ("1", "true"):
        q = q.exclude(archived_at__isnull=True)
    else:
        q = q.filter(archived_at__isnull=True)
    if not request.readonly:'''

content = content.replace(old, new, 1)

with open("/app/hc/api/views.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. ping: return 410 when check is archived
###############################################################################

python3 << 'PATCH2'
with open("/app/hc/api/views.py", "r") as f:
    content = f.read()

old = '''    if check is None:
        try:
            check = Check.objects.get(code=code)
        except Check.DoesNotExist:
            return HttpResponseNotFound("not found")

    if exitstatus is not None and exitstatus > 255:'''

new = '''    if check is None:
        try:
            check = Check.objects.get(code=code)
        except Check.DoesNotExist:
            return HttpResponseNotFound("not found")

    if getattr(check, "archived_at", None) is not None:
        return HttpResponse(status=410)

    if exitstatus is not None and exitstatus > 255:'''

content = content.replace(old, new, 1)

with open("/app/hc/api/views.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 4. Add API views for archive, restore, archive-history
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("POST")
@csrf_exempt
@authorize
def check_archive(request: ApiRequest, code: UUID) -> HttpResponse:
    from hc.api.models import ArchiveLog

    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    if check.archived_at is not None:
        return JsonResponse({"error": "check already archived"}, status=400)

    check.archived_at = now()
    check.save()

    by = (request.project.owner.email or "") if getattr(request.project, "owner_id", None) else ""
    if request.json and isinstance(request.json, dict) and request.json.get("reason"):
        by = str(request.json.get("reason", ""))[:200]
    ArchiveLog.objects.create(owner=check, action="archived", by=by)

    return JsonResponse(check.to_dict(v=request.v))


@cors("POST")
@csrf_exempt
@authorize
def check_restore(request: ApiRequest, code: UUID) -> HttpResponse:
    from hc.api.models import ArchiveLog

    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    if check.archived_at is None:
        return JsonResponse({"error": "check is not archived"}, status=400)

    if request.project.num_checks_available() <= 0:
        return JsonResponse({"error": "project has no checks available"}, status=400)

    check.archived_at = None
    check.status = "new"
    check.last_start = None
    check.last_ping = None
    check.alert_after = None
    check.last_duration = None
    check.n_pings = 0
    check.save()

    by = (request.project.owner.email or "") if getattr(request.project, "owner_id", None) else ""
    ArchiveLog.objects.create(owner=check, action="restored", by=by)

    return JsonResponse(check.to_dict(v=request.v))


@cors("GET")
@csrf_exempt
@authorize_read
def check_archive_history(request: ApiRequest, code: UUID) -> HttpResponse:
    from hc.api.models import ArchiveLog

    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    logs = ArchiveLog.objects.filter(owner=check)
    return JsonResponse({"archive_history": [t.to_dict() for t in logs]})
VIEWEOF

###############################################################################
# 5. Add URL routes
###############################################################################

python3 << 'PATCH3'
with open("/app/hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("channels/", views.channels),'

new = '''    path("checks/<uuid:code>/archive/", views.check_archive, name="hc-api-archive"),
    path("checks/<uuid:code>/restore/", views.check_restore, name="hc-api-restore"),
    path("checks/<uuid:code>/archive-history/", views.check_archive_history, name="hc-api-archive-history"),
    path("channels/", views.channels),'''

content = content.replace(old, new, 1)

with open("/app/hc/api/urls.py", "w") as f:
    f.write(content)
PATCH3

###############################################################################
# 6. Create migration and apply
###############################################################################

python manage.py makemigrations api --name check_archived_archivelog 2>&1
python manage.py migrate 2>&1
