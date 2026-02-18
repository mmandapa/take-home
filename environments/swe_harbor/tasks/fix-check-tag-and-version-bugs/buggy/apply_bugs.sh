#!/bin/bash
# Introduces 3 interacting bugs into /app for the debug task.
# Run this before solution (fixes) or before tests when verifying "without solution".
set -e
cd /app

# Bug 1: models.py - tags_list() splits by comma instead of space
python3 << 'BUG1'
with open("hc/api/models.py", "r") as f:
    content = f.read()
old = 'return [t.strip() for t in self.tags.split(" ") if t.strip()]'
new = 'return [t.strip() for t in self.tags.split(",") if t.strip()]'
if old not in content:
    raise SystemExit("Bug1: pattern not found")
content = content.replace(old, new, 1)
with open("hc/api/models.py", "w") as f:
    f.write(content)
BUG1

# Bug 2: views.py - remove precise tag filtering in get_checks()
python3 << 'BUG2'
with open("hc/api/views.py", "r") as f:
    content = f.read()
old = """    checks = []
    for check in q:
        # precise, final filtering
        if not tags or check.matches_tag_set(tags):
            checks.append(check.to_dict(readonly=request.readonly, v=request.v))"""
new = """    checks = []
    for check in q:
        checks.append(check.to_dict(readonly=request.readonly, v=request.v))"""
if old not in content:
    raise SystemExit("Bug2: pattern not found")
content = content.replace(old, new, 1)
with open("hc/api/views.py", "w") as f:
    f.write(content)
BUG2

# Bug 3: decorators.py - force API version to 1 for authorize_read
python3 << 'BUG3'
with open("hc/api/decorators.py", "r") as f:
    content = f.read()
old = "request.v = _get_api_version(request)"
new = "request.v = 1"
if old not in content:
    raise SystemExit("Bug3: pattern not found")
# Only replace in authorize_read (first occurrence is in authorize, second in authorize_read)
# We need to replace the one in authorize_read. Both use the same line.
# Replace the second occurrence.
idx = content.find(old)
if idx == -1:
    raise SystemExit("Bug3: pattern not found")
idx2 = content.find(old, idx + 1)
if idx2 == -1:
    raise SystemExit("Bug3: second occurrence not found")
content = content[:idx2] + new + content[idx2 + len(old):]
with open("hc/api/decorators.py", "w") as f:
    f.write(content)
BUG3

echo "Bugs applied."
