# equities-analytics-lakehouse

Small portfolio project I put together to show I can wire up a modern data stack without reaching for Snowflake or a massive cloud bill.

Pulls ~30 days of prices for **AAPL**, **MSFT**, and **SPY** with yfinance, lands them in a local **DuckDB** file, models them in **dbt**, and there's a **Streamlit** front end with a Plotly chart. GitHub Actions runs the extract + dbt job once a day and commits the updated `warehouse.duckdb` if anything changed.

## stack

- Python 3.11 (dbt doesn't play nice with 3.14 yet)
- yfinance → DuckDB (`raw_stock_data`)
- dbt staging + two mart tables (`dim_tickers`, `fct_daily_prices`)
- Streamlit + plotly for the dashboard

## run it locally

```bash
git clone git@github.com:Rickyganta/equities-analytics-lakehouse.git
cd equities-analytics-lakehouse

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.extract
dbt build --project-dir dbt_project --profiles-dir dbt_project
streamlit run src/app.py
```

If the app complains about missing tables, you skipped the dbt step. If extract fails, yfinance is probably rate-limiting you — wait a minute and try again.

## what's in the repo

- `src/extract.py` — download + load raw table
- `src/app.py` — dashboard
- `dbt_project/` — models live here
- `data/warehouse.duckdb` — the actual database (checked in on purpose so the demo works out of the box)
- `.github/workflows/daily_run.yml` — cron @ 12:00 UTC

## github actions note

Repo needs **Settings → Actions → General → Workflow permissions → Read and write** or the bot can't push the duckdb file back.

## columns

Raw table uses lowercase snake_case: `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`, `extracted_at`. dbt marts keep the same naming so nothing breaks between layers.

## fact table math

`daily_return_percentage` = `(close - open) / open * 100`. Intraday only, not vs prior close.

— Ricky
