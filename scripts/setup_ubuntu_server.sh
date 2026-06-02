#!/usr/bin/env bash
# Run on rj-nitro (Ubuntu) as user ricky after SSH key can push to GitHub.
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:Rickyganta/duckdb-equities-pipeline.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/duckdb-equities-pipeline}"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 6 * * *}"
LOG_DIR="${LOG_DIR:-$HOME/logs}"

echo "==> install dir: $INSTALL_DIR"
echo "==> repo: $REPO_URL"

if ! command -v git >/dev/null; then
  sudo apt update
  sudo apt install -y git python3.11 python3.11-venv
fi

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" pull --ff-only origin main
fi

cd "$INSTALL_DIR"

if [[ ! -d .venv ]]; then
  python3.11 -m venv .venv
fi

source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

dbt deps --project-dir dbt_project --profiles-dir dbt_project

chmod +x run_pipeline.sh

mkdir -p "$LOG_DIR"

CRON_LINE="$CRON_SCHEDULE $INSTALL_DIR/run_pipeline.sh >> $LOG_DIR/equities-pipeline.log 2>&1"
( crontab -l 2>/dev/null | grep -Fv "run_pipeline.sh" || true
  echo "$CRON_LINE"
) | crontab -

echo "==> cron installed:"
crontab -l | grep run_pipeline.sh

echo "==> test pipeline once (optional): $INSTALL_DIR/run_pipeline.sh"
echo "Done. Logs: $LOG_DIR/equities-pipeline.log"
