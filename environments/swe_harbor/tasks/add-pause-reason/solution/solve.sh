#!/bin/bash
set -e

###############################################################################
# 1. Add pause_reason field to Check model
###############################################################################

cd /app

python3 << 'PATCH1'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = """    status = models.CharField(max_length=6, choices=STATUSES, default="new")

    class Meta:"""
new = """    status = models.CharField(max_length=6, choices=STATUSES, default="new")
    pause_reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:"""
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 2. Add pause_reason to Check.to_dict()
###############################################################################

python3 << 'PATCH2'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = """            "manual_resume": self.manual_resume,
            "methods": self.methods,"""
new = """            "manual_resume": self.manual_resume,
            "pause_reason": self.pause_reason,
            "methods": self.methods,"""
content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 3. Extend pause view to accept and store reason
###############################################################################

python3 << 'PATCH3'
with open("hc/api/views.py", "r") as f:
    content = f.read()

old = """    # Track the status change for correct downtime calculation in Check.downtimes()
    check.create_flip("paused", mark_as_processed=True)

    check.status = "paused"
    check.last_start = None
    check.alert_after = None
    check.save()"""
new = """    # Track the status change for correct downtime calculation in Check.downtimes()
    check.create_flip("paused", mark_as_processed=True)

    reason = request.json.get("reason", "")
    if not isinstance(reason, str):
        return JsonResponse({"error": "reason must be a string"}, status=400)
    if len(reason) > 200:
        return JsonResponse({"error": "reason too long"}, status=400)

    check.status = "paused"
    check.pause_reason = reason
    check.last_start = None
    check.alert_after = None
    check.save()"""
content = content.replace(old, new, 1)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH3

###############################################################################
# 4. Extend resume view to clear pause_reason
###############################################################################

python3 << 'PATCH4'
with open("hc/api/views.py", "r") as f:
    content = f.read()

# Resume view is the only place that sets check.last_ping = None
old = """    check.status = "new"
    check.last_start = None
    check.last_ping = None
    check.alert_after = None
    check.save()"""
new = """    check.status = "new"
    check.pause_reason = ""
    check.last_start = None
    check.last_ping = None
    check.alert_after = None
    check.save()"""
content = content.replace(old, new, 1)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH4

###############################################################################
# 5. Migration
###############################################################################

cd /app
python manage.py makemigrations api --name pausereason 2>&1
python manage.py migrate 2>&1
