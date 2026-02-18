#!/bin/bash
cd /app

mkdir -p /logs/verifier

# Run migrations in case the solution created new ones
python manage.py migrate --run-syncdb > /dev/null 2>&1

PYTHONPATH=/app DJANGO_SETTINGS_MODULE=hc.settings pytest /tests/test_solution.py -v 2>&1

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
