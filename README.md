# duckdb-equities-pipeline

Portfolio project I built to show I can run a small modern data stack end to end without spinning up Snowflake or a big cloud bill.

Every day it pulls about 30 days of prices for AAPL, MSFT, and SPY (yfinance), stores them in a local DuckDB file, models the data in dbt, and serves a Streamlit dashboard with charts, backtesting, and forecasts. GitHub Actions runs the pipeline on a schedule and commits the updated warehouse when data changes.

## what it does

- ingest OHLCV from yfinance into `raw_stock_data`
- clean and model in dbt (staging + star schema marts)
- incremental fact table with SMA, rolling volatility, volume anomaly flags
- Streamlit app with candlesticks, SMA backtester, 7-day forecast, data quality ops
- daily GitHub Actions job (extract + dbt + push warehouse)

## stack

- Python 3.11
- DuckDB
- dbt + dbt-duckdb
- Streamlit, Plotly, scikit-learn, statsmodels

## run locally

```bash
git clone git@github.com:Rickyganta/duckdb-equities-pipeline.git
cd duckdb-equities-pipeline

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.extract
dbt build --project-dir dbt_project --profiles-dir dbt_project
streamlit run src/app.py
```

If Streamlit says marts are missing, run the dbt step. If extract fails, yfinance might be rate limiting you. Wait a minute and try again.

## repo layout

- `src/extract.py` - download and load raw data
- `src/app.py` - dashboard (4 tabs)
- `dbt_project/` - dbt models
- `data/warehouse.duckdb` - checked in so the demo works out of the box
- `.github/workflows/daily_run.yml` - cron at 12:00 UTC

## GitHub Actions

Turn on **Settings > Actions > General > Workflow permissions > Read and write** so the bot can push `warehouse.duckdb` back after each run.

## schema notes

Raw columns: `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`, `extracted_at`

Mart fact table includes `daily_return_percentage` = (close - open) / open * 100 (intraday, not vs prior close).

Ricky
