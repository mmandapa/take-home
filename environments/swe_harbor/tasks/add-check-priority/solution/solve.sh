#!/bin/bash
set -e

cd /app

###############################################################################
# 1. models.py: Add priority field to Check, CheckDict, and to_dict()
###############################################################################

python3 << 'PATCH_MODELS'
with open("hc/api/models.py", "r") as f:
    content = f.read()

# Add priority field after status (before "class Meta")
content = content.replace(
    "    status = models.CharField(max_length=6, choices=STATUSES, default=\"new\")\n\n    class Meta:",
    "    status = models.CharField(max_length=6, choices=STATUSES, default=\"new\")\n    priority = models.IntegerField(default=1)  # 0=low, 1=normal, 2=high\n\n    class Meta:",
    1,
)

# Add priority to CheckDict (after "tz: str")
content = content.replace(
    "    tz: str\n    ping_url: str",
    "    tz: str\n    priority: int\n    ping_url: str",
    1,
)

# Add priority to to_dict result (after "status" line in result dict)
content = content.replace(
    '            "status": self.get_status(with_started=with_started),\n            "started": self.last_start is not None,',
    '            "status": self.get_status(with_started=with_started),\n            "priority": self.priority,\n            "started": self.last_start is not None,',
    1,
)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH_MODELS

###############################################################################
# 2. views.py: Add priority to Spec, _update(), and get_checks() ordering
###############################################################################

python3 << 'PATCH_VIEWS'
with open("hc/api/views.py", "r") as f:
    content = f.read()

# Add priority to Spec (after tags line)
content = content.replace(
    "    tags: str | None = None\n    timeout: td | None = Field(None, ge=60, le=31536000)",
    "    tags: str | None = None\n    priority: int | None = Field(None, ge=0, le=2)\n    timeout: td | None = Field(None, ge=60, le=31536000)",
    1,
)

# Add "priority" to _update() for key in (...) tuple
content = content.replace(
    '    for key in (\n        "slug",\n        "tags",\n        "desc",\n        "manual_resume",\n        "methods",\n        "tz",\n        "start_kw",\n        "success_kw",\n        "failure_kw",\n        "filter_subject",\n        "filter_body",\n        "grace",\n    ):',
    '    for key in (\n        "slug",\n        "tags",\n        "desc",\n        "manual_resume",\n        "methods",\n        "tz",\n        "start_kw",\n        "success_kw",\n        "failure_kw",\n        "filter_subject",\n        "filter_body",\n        "grace",\n        "priority",\n    ):',
    1,
)

# Add order_by in get_checks() before the loop (after slug filter)
content = content.replace(
    "    if slug := request.GET.get(\"slug\"):\n        q = q.filter(slug=slug)\n\n    checks = []",
    "    if slug := request.GET.get(\"slug\"):\n        q = q.filter(slug=slug)\n\n    q = q.order_by(\"-priority\", \"name\")\n\n    checks = []",
    1,
)

with open("hc/api/views.py", "w") as f:
    f.write(content)
PATCH_VIEWS

###############################################################################
# 3. Create migration and run it
###############################################################################

python manage.py makemigrations api --name check_priority 2>&1
python manage.py migrate 2>&1
