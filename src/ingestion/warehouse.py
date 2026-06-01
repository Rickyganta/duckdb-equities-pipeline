import logging
from pathlib import Path

import duckdb
import pandas as pd

from src.config import DB_PATH, RAW_TABLE

log = logging.getLogger(__name__)


def write_raw_table(df: pd.DataFrame, db_path: Path = DB_PATH, table: str = RAW_TABLE) -> bool:
    if df.empty:
        log.error("empty dataframe — nothing to write")
        return False

    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with duckdb.connect(str(db_path)) as conn:
            conn.register("incoming", df)
            conn.execute(
                f"""
                create or replace table {table} as
                select
                    cast(symbol as varchar) as symbol,
                    cast(date as date) as date,
                    cast(open as double) as open,
                    cast(high as double) as high,
                    cast(low as double) as low,
                    cast(close as double) as close,
                    cast(volume as bigint) as volume,
                    cast(extracted_at as timestamp) as extracted_at
                from incoming
                """
            )
            count = conn.execute(f"select count(*) from {table}").fetchone()[0]
        log.info("wrote %s rows to %s", count, db_path)
        return True
    except duckdb.Error as exc:
        log.error("duckdb write failed: %s", exc)
        return False
