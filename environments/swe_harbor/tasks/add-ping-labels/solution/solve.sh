#!/bin/bash
set -e

###############################################################################
# 1. Add PingLabel model at end of hc/api/models.py
###############################################################################

cat >> /app/hc/api/models.py << 'PYEOF'


class PingLabel(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="ping_labels")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        unique_together = [["owner", "name"]]

    def to_dict(self) -> dict:
        return {"uuid": str(self.code), "name": self.name}
PYEOF

###############################################################################
# 2. Add label FK to Ping and extend Ping.to_dict()
###############################################################################

cd /app

python3 << 'PATCH1'
with open("hc/api/models.py", "r") as f:
    content = f.read()

# Add label field to Ping class after rid
old = """    rid = models.UUIDField(null=True)

    def to_dict(self) -> PingDict:"""
new = """    rid = models.UUIDField(null=True)
    label = models.ForeignKey("PingLabel", null=True, blank=True, on_delete=models.SET_NULL, related_name="pings")

    def to_dict(self) -> PingDict:"""
content = content.replace(old, new, 1)

# Add "label" to Ping.to_dict() result
old2 = """            "rid": self.rid,
            "body_url": body_url,
        }

        duration = self.duration"""
new2 = """            "rid": self.rid,
            "body_url": body_url,
            "label": self.label.name if self.label else None,
        }

        duration = self.duration"""
content = content.replace(old2, new2, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. Update Check.ping() to accept label and set ping.label
###############################################################################

python3 << 'PATCH2'
with open("hc/api/models.py", "r") as f:
    content = f.read()

# Add label param to Check.ping() signature
old = """        rid: uuid.UUID | None,
        exitstatus: int | None = None,
    ) -> None:"""
new = """        rid: uuid.UUID | None,
        exitstatus: int | None = None,
        label: "PingLabel | None" = None,
    ) -> None:"""
content = content.replace(old, new, 1)

# Set ping.label before ping.save() in Check.ping()
old2 = """            ping.rid = rid
            ping.exitstatus = exitstatus
            ping.save()"""
new2 = """            ping.rid = rid
            ping.exitstatus = exitstatus
            ping.label = label
            ping.save()"""
content = content.replace(old2, new2, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 4. Update views.ping() to pass label from GET param
###############################################################################

python3 << 'PATCH3'
with open("hc/api/views.py", "r") as f:
    content = f.read()

old = """    rid, rid_str = None, request.GET.get("rid")
    if rid_str is not None:
        if not is_valid_uuid_string(rid_str):
            return HttpResponseBadRequest("invalid uuid format")
        rid = UUID(rid_str)

    check.ping(remote_addr, scheme, method, ua, body, action, rid, exitstatus)"""
new = """    rid, rid_str = None, request.GET.get("rid")
    if rid_str is not None:
        if not is_valid_uuid_string(rid_str):
            return HttpResponseBadRequest("invalid uuid format")
        rid = UUID(rid_str)

    label = None
    label_name = request.GET.get("label")
    if label_name:
        from hc.api.models import PingLabel
        try:
            label = PingLabel.objects.get(owner=check, name=label_name)
        except PingLabel.DoesNotExist:
            pass

    check.ping(remote_addr, scheme, method, ua, body, action, rid, exitstatus, label=label)"""
content = content.replace(old, new, 1)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH3

###############################################################################
# 5. Add labels views and check_labels dispatcher
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@authorize_read
def list_labels(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import PingLabel

    q = PingLabel.objects.filter(owner=check)
    return JsonResponse({"labels": [lb.to_dict() for lb in q]})


@authorize
def create_label(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import PingLabel

    name = request.json.get("name")
    if name is None or (isinstance(name, str) and name.strip() == ""):
        return JsonResponse({"error": "name is required"}, status=400)
    if not isinstance(name, str):
        return JsonResponse({"error": "name is required"}, status=400)
    name = name.strip()
    if len(name) > 100:
        return JsonResponse({"error": "name too long"}, status=400)

    if PingLabel.objects.filter(owner=check, name=name).exists():
        return JsonResponse({"error": "label already exists"}, status=409)

    label = PingLabel(owner=check, name=name)
    label.save()
    return JsonResponse(label.to_dict(), status=201)


@csrf_exempt
@cors("GET", "POST")
def check_labels(request: HttpRequest, code: UUID) -> HttpResponse:
    if request.method == "POST":
        return create_label(request, code)
    return list_labels(request, code)
VIEWEOF

###############################################################################
# 6. Add URL route
###############################################################################

python3 << 'PATCH4'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '''    path("channels/", views.channels),'''
new = '''    path("checks/<uuid:code>/labels/", views.check_labels, name="hc-api-labels"),
    path("channels/", views.channels),'''
content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH4

###############################################################################
# 7. Migration
###############################################################################

cd /app
python manage.py makemigrations api --name pinglabel 2>&1
python manage.py migrate 2>&1
