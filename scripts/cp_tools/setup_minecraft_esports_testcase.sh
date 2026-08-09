#!/usr/bin/env bash
set -euo pipefail

# Create the source-to-knowledge MVP test structure for the Minecraft Esports
# golden scenario.
#
# Usage:
#   ./scripts/setup_minecraft_esports_testcase.sh
#   ./scripts/setup_minecraft_esports_testcase.sh /path/to/cpKnowledgeTools
#
# The script is idempotent:
# - directories are created if missing;
# - existing fixture/golden files are not overwritten;
# - placeholder files are only created when a path does not yet exist.

REPO_ROOT="${1:-$(pwd)}"

if [[ ! -f "${REPO_ROOT}/pyproject.toml" ]]; then
  echo "ERROR: ${REPO_ROOT} does not look like the cpKnowledgeTools repository root."
  echo "Expected: ${REPO_ROOT}/pyproject.toml"
  exit 1
fi

TESTS_ROOT="${REPO_ROOT}/tests"
CASE_ROOT="${TESTS_ROOT}/fixtures/source_to_knowledge/minecraft_esports"
GOLDEN_ROOT="${TESTS_ROOT}/golden/source_to_knowledge/minecraft_esports"
E2E_ROOT="${TESTS_ROOT}/e2e/source_to_knowledge"

MATERIALIZATIONS=(
  "html"
  "docx"
  "pdf"
  "eml"
  "mbox"
)

echo "Creating Minecraft Esports source-to-knowledge test structure in:"
echo "  ${REPO_ROOT}"

# ---------------------------------------------------------------------------
# Fixture materializations
# ---------------------------------------------------------------------------

for materialization in "${MATERIALIZATIONS[@]}"; do
  mkdir -p "${CASE_ROOT}/${materialization}"
done

# Initial HTML reference materialization.
HTML_FIXTURES=(
  "01-program-proposal.html"
  "02-school-response.html"
  "03-pilot-status.html"
)

for fixture in "${HTML_FIXTURES[@]}"; do
  fixture_path="${CASE_ROOT}/html/${fixture}"
  if [[ ! -e "${fixture_path}" ]]; then
    : > "${fixture_path}"
    echo "Created placeholder: ${fixture_path#${REPO_ROOT}/}"
  fi
done

# Future materializations are deliberately empty for now, but .gitkeep makes
# the intended structure visible in Git.
for materialization in "docx" "pdf" "eml" "mbox"; do
  gitkeep="${CASE_ROOT}/${materialization}/.gitkeep"
  if [[ ! -e "${gitkeep}" ]]; then
    : > "${gitkeep}"
  fi
done

# ---------------------------------------------------------------------------
# Golden expectations
# ---------------------------------------------------------------------------

mkdir -p "${GOLDEN_ROOT}"

README_PATH="${GOLDEN_ROOT}/README.md"
EXPECTED_PATH="${GOLDEN_ROOT}/EXPECTED.md"

if [[ ! -e "${README_PATH}" ]]; then
  cat > "${README_PATH}" <<'EOF'
# Minecraft Esports Source-to-Knowledge Golden Case

This directory contains the format-neutral golden expectations for the
Minecraft Esports mini-dossier.

Executable source fixtures live under:

`tests/fixtures/source_to_knowledge/minecraft_esports/`

The expected semantic model must never be consumed as source input by the
pipeline under test.
EOF
  echo "Created: ${README_PATH#${REPO_ROOT}/}"
fi

if [[ ! -e "${EXPECTED_PATH}" ]]; then
  cat > "${EXPECTED_PATH}" <<'EOF'
# Expected Semantic Results

This file is test-harness input, not source evidence.

The detailed expected Entities, Claims, Events, Evidence Links, time roles,
epistemic states, conflicts, policy outcomes, Publication Unit projection and
rebuild expectations are to be defined here.
EOF
  echo "Created: ${EXPECTED_PATH#${REPO_ROOT}/}"
fi

# Reserved location for later machine-readable expected results.
MACHINE_EXPECTED_ROOT="${GOLDEN_ROOT}/expected"
mkdir -p "${MACHINE_EXPECTED_ROOT}"

if [[ ! -e "${MACHINE_EXPECTED_ROOT}/.gitkeep" ]]; then
  : > "${MACHINE_EXPECTED_ROOT}/.gitkeep"
fi

# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------

mkdir -p "${E2E_ROOT}"

E2E_PLACEHOLDER="${E2E_ROOT}/.gitkeep"
if [[ ! -e "${E2E_PLACEHOLDER}" ]]; then
  : > "${E2E_PLACEHOLDER}"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

cat <<EOF

Created/verified structure:

tests/
├── fixtures/
│   └── source_to_knowledge/
│       └── minecraft_esports/
│           ├── html/
│           │   ├── 01-program-proposal.html
│           │   ├── 02-school-response.html
│           │   └── 03-pilot-status.html
│           ├── docx/
│           ├── pdf/
│           ├── eml/
│           └── mbox/
├── golden/
│   └── source_to_knowledge/
│       └── minecraft_esports/
│           ├── README.md
│           ├── EXPECTED.md
│           └── expected/
└── e2e/
    └── source_to_knowledge/

No existing fixture or golden file was overwritten.
EOF
