#!/bin/bash
set -e
cd /app

###############################################################################
# 1. Add CloneLog model to hc/api/models.py
###############################################################################

cat >> /app/hc/api/models.py << 'PYEOF'


class CloneLog(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    source_check = models.ForeignKey(
        Check, models.CASCADE, related_name="clone_operations_as_source"
    )
    cloned_check = models.ForeignKey(
        Check, models.CASCADE, related_name="clone_operations_as_clone"
    )
    target_project = models.ForeignKey(
        "accounts.Project", models.SET_NULL, null=True, related_name="+"
    )
    created = models.DateTimeField(default=now)
    cloned_by = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "source_check": str(self.source_check.code),
            "cloned_check": str(self.cloned_check.code),
            "target_project": str(self.target_project.code) if self.target_project else None,
            "created": isostring(self.created),
            "cloned_by": self.cloned_by,
        }
PYEOF

###############################################################################
# 2. Add Check.clone() method
###############################################################################

python3 << 'PATCH1'
with open("/app/hc/api/models.py", "r") as f:
    content = f.read()

old = '''    def assign_all_channels(self) -> None:
        channels = Channel.objects.filter(project=self.project)
        self.channel_set.set(channels)

    def tags_list(self) -> list[str]:'''

new = '''    def assign_all_channels(self) -> None:
        channels = Channel.objects.filter(project=self.project)
        self.channel_set.set(channels)

    def clone(self, target_project, name_override=None, cloned_by=""):
        """Clone this check to the same or another project. Creates a new check with copied config and a CloneLog entry."""
        with transaction.atomic():
            check = Check.objects.select_for_update().get(id=self.id)

            if target_project.num_checks_available() <= 0:
                raise ValueError("target project has no checks available")

            name = name_override if name_override is not None else check.name
            new_check = Check(
                project=target_project,
                name=name,
                slug=check.slug,
                tags=check.tags,
                desc=check.desc,
                kind=check.kind,
                timeout=check.timeout,
                grace=check.grace,
                schedule=check.schedule,
                tz=check.tz,
                filter_subject=check.filter_subject,
                filter_body=check.filter_body,
                start_kw=check.start_kw,
                success_kw=check.success_kw,
                failure_kw=check.failure_kw,
                methods=check.methods,
                manual_resume=check.manual_resume,
            )
            new_check.save()
            new_check.channel_set.set(Channel.objects.filter(project=target_project))
            CloneLog.objects.create(
                source_check=check,
                cloned_check=new_check,
                target_project=target_project,
                cloned_by=cloned_by,
            )
            return new_check

    def tags_list(self) -> list[str]:'''

content = content.replace(old, new, 1)

with open("/app/hc/api/models.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. Add cloned_from to Check.to_dict()
###############################################################################

python3 << 'PATCH2'
with open("/app/hc/api/models.py", "r") as f:
    content = f.read()

old = '''            result["channels"] = self.channels_str()

        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())'''

new = '''            result["channels"] = self.channels_str()

        clonelog = CloneLog.objects.filter(cloned_check=self).first()
        result["cloned_from"] = str(clonelog.source_check.code) if clonelog else None

        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())'''

content = content.replace(old, new, 1)

with open("/app/hc/api/models.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 4. Add API views for clone
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("POST")
@csrf_exempt
@authorize
def check_clone(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    target_project = request.project
    target_project_str = request.json.get("project") if request.json else None
    target_api_key = (request.json.get("target_api_key") if request.json else None) or ""

    if target_project_str is not None:
        if not is_valid_uuid_string(str(target_project_str)):
            return JsonResponse({"error": "invalid project uuid"}, status=400)
        target_uuid = UUID(str(target_project_str))
        if target_uuid == request.project.code:
            if target_api_key:
                return JsonResponse({"error": "cannot clone to same project"}, status=400)
        else:
            try:
                target_project = Project.objects.get(code=target_uuid)
            except Project.DoesNotExist:
                return HttpResponseNotFound()
            if not target_api_key or target_project.api_key != target_api_key:
                return JsonResponse({"error": "not authorized for target project"}, status=403)

    try:
        name_override = (request.json or {}).get("name")
        cloned_by = (request.project.owner.email or "") if request.project.owner_id else ""
        new_check = check.clone(target_project, name_override=name_override, cloned_by=cloned_by)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse(new_check.to_dict(v=request.v), status=201)


@cors("GET")
@csrf_exempt
@authorize_read
def check_clones(request: ApiRequest, code: UUID) -> HttpResponse:
    from hc.api.models import CloneLog

    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    logs = CloneLog.objects.filter(source_check=check)
    return JsonResponse({"clones": [t.to_dict() for t in logs]})
VIEWEOF

###############################################################################
# 5. Add URL routes
###############################################################################

python3 << 'PATCH3'
with open("/app/hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("channels/", views.channels),'

new = '''    path("checks/<uuid:code>/clone/", views.check_clone, name="hc-api-clone"),
    path("checks/<uuid:code>/clones/", views.check_clones, name="hc-api-clones"),
    path("channels/", views.channels),'''

content = content.replace(old, new, 1)

with open("/app/hc/api/urls.py", "w") as f:
    f.write(content)
PATCH3

###############################################################################
# 6. Create migration and apply
###############################################################################

python manage.py makemigrations api --name clonelog 2>&1
python manage.py migrate 2>&1
