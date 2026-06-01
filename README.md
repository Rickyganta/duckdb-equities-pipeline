# Equities Analytics Lakehouse

Portfolio Modern Data Stack: **yfinance** ingestion → **DuckDB** warehouse → **dbt** modeling → **Streamlit** dashboard, orchestrated by **GitHub Actions**.

## Architecture

```
yfinance (extract) → DuckDB (raw_stock_data)
                         ↓
                    dbt (staging + star schema marts)
                         ↓
                 Streamlit (KPIs + charts)
```

## Quick start

Use **Python 3.11 or 3.12** (dbt does not yet support 3.14).

```bash
cd Equities_Analytics_Lakehouse
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python src/extract.py
dbt build --project-dir dbt_project --profiles-dir dbt_project

streamlit run src/app.py
```

## Project layout

| Path | Purpose |
|------|---------|
| `src/extract.py` | Download 30d OHLCV for AAPL, MSFT, SPY into `data/warehouse.duckdb` |
| `dbt_project/` | Staging cleanup + `dim_tickers` / `fct_daily_prices` marts |
| `src/app.py` | Read-only Streamlit dashboard over mart tables |
| `.github/workflows/daily_run.yml` | Daily extract → dbt → commit warehouse |

## Mart schema

- **`marts.dim_tickers`** — Ticker dimension (surrogate key, company label, date range)
- **`marts.fct_daily_prices`** — Daily prices, volume, daily change and return %

## CI note

The daily workflow needs permission to push commits. Ensure the default `GITHUB_TOKEN` can write to the branch (repo **Settings → Actions → General → Workflow permissions → Read and write**).
