from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"

TICKERS = ("AAPL", "MSFT", "SPY")
PERIOD = "30d"
RAW_TABLE = "raw_stock_data"
