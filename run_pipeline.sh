#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

source .venv/bin/activate

python -m src.extract
dbt build --project-dir dbt_project --profiles-dir dbt_project

git add data/warehouse.duckdb
if git diff --staged --quiet; then
  echo "No warehouse changes to commit."
  exit 0
fi

git commit -m "Automated daily warehouse snapshot update: $(date)"
git push origin main
