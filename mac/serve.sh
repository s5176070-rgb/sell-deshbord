#!/bin/bash
# The Mac's serve.bat. launchd runs it at login (see install.sh) and restarts it
# when it falls over; the server does the daily re-analysis itself, so there is
# no second scheduled job. By hand: mac/serve.sh, then http://127.0.0.1:8765
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "ERROR: local Python environment not found at $PY - run mac/install.sh" >> daily.log
  exit 2
fi
export PYTHONIOENCODING=utf-8
echo >> daily.log
echo "==== server start $(date)" >> daily.log
"$PY" stress.py --serve --no-open >> daily.log 2>&1
rc=$?
# Exit 3 is the port guard saying something already serves 8765: an answer, not
# a failure. Report success so launchd's KeepAlive leaves it be instead of
# retrying every 30 seconds.
if [ $rc -eq 3 ]; then
  echo "==== already running elsewhere, not restarting" >> daily.log
  exit 0
fi
echo "==== exited $(date) with $rc, launchd restarts it" >> daily.log
exit $rc
