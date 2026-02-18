#!/bin/bash
set -e

###############################################################################
# 1. Add ActivityLog model and .log() helper to hc/api/models.py
###############################################################################

cat >> /app/hc/api/models.py << 'PYEOF'


class ActivityLog(models.Model):
    project = models.ForeignKey(Project, models.CASCADE, related_name="activity_logs")
    action = models.CharField(max_length=50)
    check_code = models.UUIDField(null=True, blank=True)
    details = models.CharField(max_length=500, blank=True, default="")
    created = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-created"]

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "check_code": str(self.check_code) if self.check_code else None,
            "details": self.details,
            "created": isostring(self.created),
        }

    @classmethod
    def log(cls, project, action: str, check_code=None, details: str = "") -> None:
        cls.objects.create(
            project=project,
            action=action,
            check_code=check_code,
            details=details[:500] if details else "",
        )
PYEOF

###############################################################################
# 2. Add ActivityLog to views import and inject logging in create_check,
#    update_check, pause, resume
###############################################################################

cd /app

python3 << 'PATCH1'
with open("hc/api/views.py", "r") as f:
    content = f.read()

# Add ActivityLog to import
content = content.replace(
    "from hc.api.models import MAX_DURATION, Channel, Check, Flip, Notification, Ping",
    "from hc.api.models import MAX_DURATION, ActivityLog, Channel, Check, Flip, Notification, Ping",
    1,
)

# create_check: before final return, log
old1 = """    try:
        _update(check, spec, request.v)
    except BadChannelException as e:
        return JsonResponse({"error": e.message}, status=400)

    return JsonResponse(check.to_dict(v=request.v), status=201 if created else 200)"""

new1 = """    try:
        _update(check, spec, request.v)
    except BadChannelException as e:
        return JsonResponse({"error": e.message}, status=400)

    ActivityLog.log(request.project, "check_created" if created else "check_updated", check.code, check.name or "")
    return JsonResponse(check.to_dict(v=request.v), status=201 if created else 200)"""

content = content.replace(old1, new1, 1)

# update_check: before return, log
old2 = """        try:
            _update(check, spec, request.v)
        except BadChannelException as e:
            return JsonResponse({"error": e.message}, status=400)

    return JsonResponse(check.to_dict(v=request.v))"""

new2 = """        try:
            _update(check, spec, request.v)
        except BadChannelException as e:
            return JsonResponse({"error": e.message}, status=400)

    ActivityLog.log(request.project, "check_updated", check.code, check.name or "")
    return JsonResponse(check.to_dict(v=request.v))"""

content = content.replace(old2, new2, 1)

# pause: before return, log
old3 = """    # After pausing a check we must check if all checks are up,
    # and Profile.next_nag_date needs to be cleared out:
    check.project.update_next_nag_dates()

    return JsonResponse(check.to_dict(v=request.v))"""

new3 = """    # After pausing a check we must check if all checks are up,
    # and Profile.next_nag_date needs to be cleared out:
    check.project.update_next_nag_dates()

    ActivityLog.log(request.project, "check_paused", check.code, check.name or "")
    return JsonResponse(check.to_dict(v=request.v))"""

content = content.replace(old3, new3, 1)

# resume: before return, log
old4 = """    check.status = "new"
    check.last_start = None
    check.last_ping = None
    check.alert_after = None
    check.save()

    return JsonResponse(check.to_dict(v=request.v))"""

new4 = """    check.status = "new"
    check.last_start = None
    check.last_ping = None
    check.alert_after = None
    check.save()

    ActivityLog.log(request.project, "check_resumed", check.code, check.name or "")
    return JsonResponse(check.to_dict(v=request.v))"""

content = content.replace(old4, new4, 1)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. Add list_activity view to views.py
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("GET")
@csrf_exempt
@authorize_read
def list_activity(request: ApiRequest) -> JsonResponse:
    q = ActivityLog.objects.filter(project=request.project)
    return JsonResponse({"activity": [r.to_dict() for r in q]})
VIEWEOF

###############################################################################
# 4. Add activity URL route
###############################################################################

python3 << 'PATCH2'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '''    path("channels/", views.channels),'''

new = '''    path("activity/", views.list_activity, name="hc-api-activity"),
    path("channels/", views.channels),'''

content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 5. Create migration and run it
###############################################################################

cd /app
python manage.py makemigrations api --name activitylog 2>&1
python manage.py migrate 2>&1
