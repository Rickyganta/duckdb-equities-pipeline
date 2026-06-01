"""Download market data via yfinance and load into DuckDB."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"
TICKERS = ("AAPL", "MSFT", "SPY")
LOOKBACK_DAYS = 30
TABLE_NAME = "raw_stock_data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def fetch_ticker_history(ticker: str, period: str = f"{LOOKBACK_DAYS}d") -> pd.DataFrame | None:
    """Fetch historical OHLCV for a single ticker."""
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period=period, auto_adjust=True)
        if history.empty:
            logger.warning("No rows returned for ticker=%s", ticker)
            return None
        history = history.reset_index()
        history.columns = [c.lower().replace(" ", "_") for c in history.columns]
        if "date" not in history.columns and "datetime" in history.columns:
            history = history.rename(columns={"datetime": "date"})
        history["ticker"] = ticker
        history["extracted_at"] = pd.Timestamp.now("UTC")
        logger.info("Fetched %d rows for %s", len(history), ticker)
        return history
    except Exception:
        logger.exception("Failed to fetch data for ticker=%s", ticker)
        return None


def fetch_all_tickers(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Fetch and combine history for all tickers."""
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        frame = fetch_ticker_history(ticker)
        if frame is not None:
            frames.append(frame)

    if not frames:
        raise RuntimeError("No market data fetched for any ticker")

    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"], utc=True).dt.tz_localize(None)
    return combined


def load_to_duckdb(df: pd.DataFrame, db_path: Path, table_name: str) -> int:
    """Replace raw table in DuckDB with the latest extract."""
    for col in ("dividends", "stock_splits"):
        if col not in df.columns:
            df[col] = 0.0

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        conn.register("extract_df", df)
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT
                CAST(ticker AS VARCHAR) AS ticker,
                CAST(date AS DATE) AS date,
                CAST(open AS DOUBLE) AS open,
                CAST(high AS DOUBLE) AS high,
                CAST(low AS DOUBLE) AS low,
                CAST(close AS DOUBLE) AS close,
                CAST(volume AS BIGINT) AS volume,
                CAST(dividends AS DOUBLE) AS dividends,
                CAST(stock_splits AS DOUBLE) AS stock_splits,
                CAST(extracted_at AS TIMESTAMP) AS extracted_at
            FROM extract_df
            """
        )
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        logger.info("Loaded %d rows into %s.%s", row_count, db_path.name, table_name)
        return int(row_count)
    finally:
        conn.close()


def main() -> None:
    logger.info("Starting extract for tickers: %s", ", ".join(TICKERS))
    df = fetch_all_tickers(TICKERS)
    load_to_duckdb(df, DB_PATH, TABLE_NAME)
    logger.info("Extract complete -> %s", DB_PATH)


if __name__ == "__main__":
    main()
