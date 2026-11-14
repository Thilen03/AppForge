#!/usr/bin/env bash
# Local terminal entry point. Never redirect Git metadata around sandbox rules.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec python3 "$ROOT/scripts/publish_local.py" "$@"
