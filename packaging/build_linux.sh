#!/usr/bin/env bash
# Build a Linux onefile executable of opencut-pyside with PyInstaller.
#
# Run from a clean checkout on a Linux host (CI does this via
# .github/workflows/build.yml). The resulting binary lands in
# packaging/dist/opencut-pyside.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

python3 -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install pyinstaller

cd packaging
pyinstaller --clean --noconfirm opencut-pyside.spec

echo "Built: ${REPO_ROOT}/packaging/dist/opencut-pyside"
