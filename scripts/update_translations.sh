#!/usr/bin/env bash
# Regenerate .ts and .qm translation files from the current source tree.
#
# Usage:
#     ./scripts/update_translations.sh
#
# This script:
#   1. Runs pyside6-lupdate to scan every *.py file under the repo for
#      self.tr(...) / QCoreApplication.translate(...) calls and updates
#      i18n/opencut_vi.ts + opencut_en.ts with any new strings.
#   2. Runs pyside6-lrelease to compile the .ts files into .qm binaries
#      that the runtime translator loads.
#
# It is safe to run repeatedly; unchanged entries are left alone. After
# editing translations by hand, re-run this script to refresh the .qm
# files before committing.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TS_FILES=(
    "i18n/opencut_vi.ts"
    "i18n/opencut_en.ts"
)

# Collect every .py file in the app tree. We intentionally exclude the
# packaging/, scripts/ and tests/ directories — they don't contain
# user-facing strings.
mapfile -t PY_FILES < <(
    find . -type f -name "*.py" \
        -not -path "./.git/*" \
        -not -path "./.venv/*" \
        -not -path "*/__pycache__/*" \
        -not -path "./packaging/*" \
        -not -path "./scripts/*" \
        -not -path "./tests/*"
)

echo "Scanning ${#PY_FILES[@]} Python files for translatable strings..."
pyside6-lupdate "${PY_FILES[@]}" -ts "${TS_FILES[@]}"

echo "Compiling .ts -> .qm..."
for ts_file in "${TS_FILES[@]}"; do
    pyside6-lrelease "$ts_file"
done

echo "Done. Commit the updated .ts files; .qm files are generated and"
echo "intentionally gitignored (see .gitignore)."
