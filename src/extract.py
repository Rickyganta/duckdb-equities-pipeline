import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DB_PATH, TICKERS
from src.ingestion import market_data, warehouse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def extract_market_data() -> bool:
    log.info("starting extract for %s", list(TICKERS))

    df = market_data.fetch_all()
    if df is None:
        log.error("extraction failed — no data from yahoo")
        return False

    if not warehouse.write_raw_table(df, DB_PATH):
        return False

    log.info("extract finished ok")
    return True


def main():
    success = extract_market_data()
    if not success:
        if DB_PATH.exists():
            log.warning("extract failed — using existing warehouse.duckdb")
            sys.exit(0)
        log.error("extract failed and no warehouse file exists")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
