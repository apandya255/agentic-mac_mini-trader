#!/bin/bash
# Service wrapper for launchd-managed services.
# Runs the service, and when it exits, logs the restart event.
#
# Usage: service_wrapper.sh <service_name> <command> [args...]
#
# Example plist ProgramArguments:
#   <array>
#     <string>/path/to/scripts/service_wrapper.sh</string>
#     <string>serve.py</string>
#     <string>/path/to/.venv/bin/python</string>
#     <string>serve.py</string>
#   </array>
#
# Requirements: 12.4

set -euo pipefail

SERVICE_NAME="${1:?Usage: service_wrapper.sh <service_name> <command> [args...]}"
shift

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOGGER="${PROJECT_DIR}/src/data_platform/service_logger.py"

# Run the service command
"$@"
EXIT_CODE=$?

# Log the restart event (launchd will restart us after this script exits)
"$PYTHON" "$LOGGER" "$SERVICE_NAME" "$EXIT_CODE" ""

exit $EXIT_CODE
