#!/usr/bin/env bash
# Run on Ubuntu from repo root: bash scripts/verify_deployment.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

ok() { echo "  [OK]   $*"; PASS=$((PASS + 1)); }
bad() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }

echo "=== Equities pipeline deployment check ==="
echo "Repo: $REPO_ROOT"
echo

echo "1) Python 3.11+"
PYTHON=""
for cmd in python3.11 python3.12 python3; do
  if command -v "$cmd" >/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
if [[ -n "$PYTHON" ]] && "$PYTHON" -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
  ok "$PYTHON $($PYTHON --version)"
else
  bad "Python 3.11+ not found (sudo apt install -y python3 python3-venv)"
fi

echo "2) Virtual environment"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  ok ".venv exists ($(python --version))"
else
  bad ".venv missing — run: python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
fi

echo "3) Python imports"
if [[ -f .venv/bin/activate ]]; then
  if python -c "import duckdb, yfinance, dbt" 2>/dev/null; then
    ok "duckdb, yfinance, dbt importable"
  else
    bad "pip install -r requirements.txt"
  fi
fi

echo "4) dbt deps"
if [[ -d dbt_project/dbt_packages ]] || dbt deps --project-dir dbt_project --profiles-dir dbt_project >/dev/null 2>&1; then
  ok "dbt deps ready"
else
  bad "dbt deps failed"
fi

echo "5) Git remote"
if git remote get-url origin 2>/dev/null | grep -q github.com; then
  ok "origin=$(git remote get-url origin)"
else
  bad "no GitHub origin configured"
fi

echo "6) GitHub SSH authentication"
SSH_MSG="$(ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@github.com 2>&1 || true)"
if echo "$SSH_MSG" | grep -qiE "successfully authenticated|Hi "; then
  ok "GitHub SSH: ${SSH_MSG//$'\n'/ }"
else
  bad "GitHub SSH failed: $SSH_MSG"
  echo "       Fix: add ~/.ssh/id_ed25519_github.pub to GitHub, configure ~/.ssh/config Host github.com"
fi

echo "7) Git push dry-run (no changes pushed)"
if git push --dry-run origin main 2>&1 | grep -qiE "up.to.date|Everything up-to-date|main -> main|Would push"; then
  ok "git push --dry-run succeeded"
else
  PUSH_OUT="$(git push --dry-run origin main 2>&1 || true)"
  if echo "$PUSH_OUT" | grep -qi "Permission denied\|Could not read from remote"; then
    bad "git push denied: $PUSH_OUT"
  else
    ok "git push check: $PUSH_OUT"
  fi
fi

echo "8) Cron job"
CRON_LINE="$(crontab -l 2>/dev/null | grep run_pipeline.sh || true)"
if [[ -n "$CRON_LINE" ]]; then
  ok "crontab: $CRON_LINE"
else
  bad "no cron for run_pipeline.sh — run: bash scripts/setup_ubuntu_server.sh"
fi

echo "9) Pipeline script executable"
if [[ -x run_pipeline.sh ]]; then
  ok "run_pipeline.sh is executable"
else
  bad "chmod +x run_pipeline.sh"
fi

echo
echo "=== Summary: $PASS passed, $FAIL failed ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "Fix failures above, then run: ./run_pipeline.sh"
  exit 1
fi

echo "All checks passed. Run a full pipeline test with:"
echo "  ./run_pipeline.sh"
exit 0
