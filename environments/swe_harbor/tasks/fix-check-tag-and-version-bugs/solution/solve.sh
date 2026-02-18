#!/bin/bash
# Fixes the three bugs introduced by buggy/apply_bugs.sh.
# Expects bugs to already be applied (when running "with solution" flow).
set -e
cd /app

# Fix 1: models.py - tags_list() split back to space
python3 << 'FIX1'
with open("hc/api/models.py", "r") as f:
    content = f.read()
old = 'return [t.strip() for t in self.tags.split(",") if t.strip()]'
new = 'return [t.strip() for t in self.tags.split(" ") if t.strip()]'
if old not in content:
    raise SystemExit("Fix1: buggy pattern not found")
content = content.replace(old, new, 1)
with open("hc/api/models.py", "w") as f:
    f.write(content)
FIX1

# Fix 2: views.py - restore precise tag filtering in get_checks()
python3 << 'FIX2'
with open("hc/api/views.py", "r") as f:
    content = f.read()
old = """    checks = []
    for check in q:
        checks.append(check.to_dict(readonly=request.readonly, v=request.v))"""
new = """    checks = []
    for check in q:
        # precise, final filtering
        if not tags or check.matches_tag_set(tags):
            checks.append(check.to_dict(readonly=request.readonly, v=request.v))"""
if old not in content:
    raise SystemExit("Fix2: buggy pattern not found")
content = content.replace(old, new, 1)
with open("hc/api/views.py", "w") as f:
    f.write(content)
FIX2

# Fix 3: decorators.py - restore request.v = _get_api_version(request) in authorize_read
python3 << 'FIX3'
with open("hc/api/decorators.py", "r") as f:
    content = f.read()
# Restore second occurrence (authorize_read)
old = "request.v = 1"
new = "request.v = _get_api_version(request)"
idx = content.find(old)
if idx == -1:
    raise SystemExit("Fix3: buggy pattern not found")
# Replace only the second "request.v = 1" (the one we introduced in authorize_read)
idx2 = content.find(old, idx + 1)
if idx2 == -1:
    # Only one occurrence, replace it
    idx2 = idx
content = content[:idx2] + new + content[idx2 + len(old):]
with open("hc/api/decorators.py", "w") as f:
    f.write(content)
FIX3

echo "Fixes applied."
