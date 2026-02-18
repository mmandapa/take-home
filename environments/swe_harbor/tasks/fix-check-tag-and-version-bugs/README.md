# Fix Check Tag and Version Bugs (debug task)

This task uses a **buggy** codebase: run `buggy/apply_bugs.sh` before solution or tests so that the app has the bugs applied.

**With solution (should print 1):**
```bash
docker run --rm \
  -v $(pwd)/tasks/fix-check-tag-and-version-bugs/buggy:/buggy \
  -v $(pwd)/tasks/fix-check-tag-and-version-bugs/solution:/solution \
  -v $(pwd)/tasks/fix-check-tag-and-version-bugs/tests:/tests \
  swe-harbor \
  bash -c "mkdir -p /logs/verifier && bash /buggy/apply_bugs.sh && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

**Without solution (should print 0):**
```bash
docker run --rm \
  -v $(pwd)/tasks/fix-check-tag-and-version-bugs/buggy:/buggy \
  -v $(pwd)/tasks/fix-check-tag-and-version-bugs/tests:/tests \
  swe-harbor \
  bash -c "mkdir -p /logs/verifier && bash /buggy/apply_bugs.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

Run from `environments/swe_harbor/`. Use image name `swe` if you built with `docker build -t swe environment/`.
