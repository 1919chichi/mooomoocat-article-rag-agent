#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! python -c "import pytest" >/dev/null 2>&1; then
  echo "pytest is not installed. Run: python -m pip install -e '.[dev]'" >&2
  exit 1
fi

if ! command -v mooomoocatrag >/dev/null 2>&1; then
  echo "mooomoocatrag is not installed. Run: python -m pip install -e '.[dev]'" >&2
  exit 1
fi

python -m pytest -q
python -m compileall -q src tests
mooomoocatrag --help >/dev/null
git diff --check -- .
git diff --cached --check -- .
