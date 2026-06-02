#!/usr/bin/env bash
# Run on rj-nitro (Ubuntu) as user ricky after SSH key can push to GitHub.
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:Rickyganta/duckdb-equities-pipeline.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/duckdb-equities-pipeline}"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 6 * * *}"
LOG_DIR="${LOG_DIR:-$HOME/logs}"

find_python() {
  local cmd ver major minor
  for cmd in python3.11 python3.12 python3; do
    if command -v "$cmd" >/dev/null; then
      ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      major="${ver%%.*}"
      minor="${ver#*.}"
      if [[ "$major" -eq 3 && "$minor" -ge 11 ]]; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

echo "==> install dir: $INSTALL_DIR"
echo "==> repo: $REPO_URL"

if ! command -v git >/dev/null; then
  sudo apt update
  sudo apt install -y git python3 python3-venv python3-pip
fi

PYTHON="$(find_python || true)"
if [[ -z "${PYTHON:-}" ]]; then
  echo "ERROR: need Python 3.11+. On Ubuntu 24.04 run:"
  echo "  sudo apt update && sudo apt install -y python3 python3-venv"
  echo "Or for 3.11 specifically: sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt install -y python3.11 python3.11-venv"
  exit 1
fi

echo "==> using $PYTHON ($($PYTHON --version))"

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" pull --ff-only origin main
fi

cd "$INSTALL_DIR"

if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
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
