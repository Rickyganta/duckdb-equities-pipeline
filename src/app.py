"""Streamlit dashboard for equities analytics mart."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"


@st.cache_resource
def get_connection(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def run_query(conn: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return conn.execute(sql).fetchdf()


def main() -> None:
    st.set_page_config(
        page_title="Equities Analytics Lakehouse",
        page_icon="📈",
        layout="wide",
    )
    st.title("Equities Analytics Lakehouse")
    st.caption("Modern Data Stack demo — DuckDB · dbt · Streamlit")

    if not DB_PATH.exists():
        st.error(
            f"Warehouse not found at `{DB_PATH}`. "
            "Run `python src/extract.py` and `dbt build --project-dir dbt_project --profiles-dir dbt_project` first."
        )
        st.stop()

    conn = get_connection(str(DB_PATH))

    try:
        dim = run_query(conn, "SELECT * FROM marts.dim_tickers ORDER BY ticker")
        facts = run_query(
            conn,
            """
            SELECT
                f.ticker,
                d.company_name,
                f.trade_date,
                f.close_price,
                f.volume,
                f.daily_return_pct
            FROM marts.fct_daily_prices f
            JOIN marts.dim_tickers d ON f.ticker_sk = d.ticker_sk
            ORDER BY f.ticker, f.trade_date
            """,
        )
    except duckdb.CatalogException as exc:
        st.error(f"Mart tables missing: {exc}")
        st.info("Build models with dbt before opening the dashboard.")
        st.stop()

    if facts.empty:
        st.warning("No fact data available.")
        st.stop()

    latest = (
        facts.sort_values("trade_date")
        .groupby("ticker", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )

    st.subheader("Key metrics (latest session)")
    cols = st.columns(len(latest))
    for col, row in zip(cols, latest.itertuples(index=False)):
        ret = row.daily_return_pct
        ret_label = f"{ret:+.2f}%" if pd.notna(ret) else "N/A"
        col.metric(
            label=f"{row.ticker} — {row.company_name}",
            value=f"${row.close_price:,.2f}",
            delta=ret_label,
        )

    st.subheader("Universe")
    st.dataframe(dim, use_container_width=True, hide_index=True)

    st.subheader("Price trends")
    tickers = sorted(facts["ticker"].unique())
    selected = st.multiselect("Tickers", tickers, default=tickers)
    chart_df = facts[facts["ticker"].isin(selected)].copy()
    chart_df["trade_date"] = pd.to_datetime(chart_df["trade_date"])
    chart_pivot = (
        chart_df.pivot(index="trade_date", columns="ticker", values="close_price")
        .sort_index()
    )
    st.line_chart(chart_pivot, use_container_width=True)

    with st.expander("Raw fact detail"):
        st.dataframe(
            facts.sort_values(["ticker", "trade_date"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
