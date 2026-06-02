from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"

TICKERS = (
    "AAPL",
    "MSFT",
    "SPY",
    "NVDA",
    "AMD",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "QQQ",
)
PERIOD = "60d"
RAW_TABLE = "raw_stock_data"
