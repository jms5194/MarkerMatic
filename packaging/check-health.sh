#!/bin/sh
echo "Launching MarkerMatic"

"$1" --check-health &
pid=$!

sleep 60
kill "$pid" 2>/dev/null
wait "$pid"
exit_code=$?

if [ "$exit_code" -eq 0 ]; then
    echo "Health check completed successfully"
    exit 0
else
    echo "Health check failed with exit code $exit_code"
    exit 1
fi