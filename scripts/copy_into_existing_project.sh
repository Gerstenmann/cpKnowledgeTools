#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/cpKnowledgeSystem" >&2
  exit 2
fi

PROJECT_ROOT="$1"
BUNDLE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$PROJECT_ROOT" ]]; then
  echo "Project root does not exist: $PROJECT_ROOT" >&2
  exit 2
fi

mkdir -p "$PROJECT_ROOT/src/cpknowledgesystem" "$PROJECT_ROOT/tests"
cp -R "$BUNDLE_ROOT/src/cpknowledgesystem/template_generator" \
      "$PROJECT_ROOT/src/cpknowledgesystem/"
cp -R "$BUNDLE_ROOT/tests/template_generator" \
      "$PROJECT_ROOT/tests/"

if [[ ! -f "$PROJECT_ROOT/src/cpknowledgesystem/__init__.py" ]]; then
  printf '%s\n' '"""cpKnowledgeSystem Python package."""' \
    > "$PROJECT_ROOT/src/cpknowledgesystem/__init__.py"
fi

cat <<MESSAGE
Template Generator copied to:
  $PROJECT_ROOT/src/cpknowledgesystem/template_generator
  $PROJECT_ROOT/tests/template_generator

Next steps:
  cd "$PROJECT_ROOT"
  python -m pip install "PyYAML>=6.0,<7.0" pytest
  python -m pip install -e .
  python -m cpknowledgesystem.template_generator list
MESSAGE
