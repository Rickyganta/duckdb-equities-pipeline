import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.config import DB_PATH, TICKERS

log = logging.getLogger(__name__)

FACT_SQL = """
select
    symbol,
    date,
    open,
    high,
    low,
    close,
    volume,
    daily_return_percentage,
    sma_7,
    sma_21,
    rolling_volatility_30,
    volume_anomaly_flag
from marts.fct_daily_prices
order by symbol, date
"""

ANOMALY_SQL = """
select
    symbol,
    date,
    open,
    high,
    low,
    close,
    volume,
    daily_return_percentage,
    rolling_volatility_30,
    volume_anomaly_flag
from marts.fct_daily_prices
where volume_anomaly_flag = 1
order by date desc, symbol
limit 50
"""


@st.cache_resource
def connect(db_path: str):
    return duckdb.connect(db_path, read_only=True)


@st.cache_data(ttl=300)
def load_facts(db_path: str) -> pd.DataFrame:
    conn = connect(db_path)
    return conn.execute(FACT_SQL).fetchdf()


@st.cache_data(ttl=300)
def load_anomalies(db_path: str) -> pd.DataFrame:
    conn = connect(db_path)
    return conn.execute(ANOMALY_SQL).fetchdf()


def build_candlestick_chart(ticker_df: pd.DataFrame, symbol: str) -> go.Figure:
    df = ticker_df.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"])
    df["volume_color"] = df.apply(
        lambda r: "#26a69a" if r["close"] >= r["open"] else "#ef5350",
        axis=1,
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.72, 0.28],
    )

    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="ohlc",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["sma_7"],
            mode="lines",
            name="sma_7",
            line=dict(color="#2196f3", width=1.5),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["sma_21"],
            mode="lines",
            name="sma_21",
            line=dict(color="#ff9800", width=1.5),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=df["date"],
            y=df["volume"],
            name="volume",
            marker_color=df["volume_color"],
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"{symbol} — candlestick + moving averages",
        template="plotly_white",
        height=650,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_yaxes(title_text="price", row=1, col=1)
    fig.update_yaxes(title_text="volume", row=2, col=1)
    fig.update_xaxes(title_text="date", row=2, col=1)

    return fig


def main():
    st.set_page_config(page_title="Equities Lakehouse", layout="wide")
    st.title("Equities Analytics Lakehouse")
    st.caption("duckdb · dbt incremental marts · streamlit")

    try:
        if not DB_PATH.exists():
            raise FileNotFoundError(
                "no warehouse.duckdb yet — run extract + dbt first"
            )

        facts = load_facts(str(DB_PATH))
        if facts.empty:
            st.warning("fact table is empty")
            return

        selected = st.sidebar.selectbox("ticker", list(TICKERS), index=0)
        ticker_df = facts[facts["symbol"] == selected].copy()

        if ticker_df.empty:
            st.warning(f"no rows for {selected}")
            return

        latest = ticker_df.sort_values("date").iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("close", f"${latest['close']:,.2f}")
        c2.metric("daily return", f"{latest['daily_return_percentage']:+.2f}%")
        c3.metric("sma_7", f"${latest['sma_7']:,.2f}" if pd.notna(latest["sma_7"]) else "n/a")
        c4.metric("volatility (30d)", f"{latest['rolling_volatility_30']:.2f}" if pd.notna(latest["rolling_volatility_30"]) else "n/a")

        st.plotly_chart(
            build_candlestick_chart(ticker_df, selected),
            use_container_width=True,
        )

        st.subheader("volume anomalies")
        st.caption("days where volume > 2x the 30-day rolling average")
        anomalies = load_anomalies(str(DB_PATH))
        if anomalies.empty:
            st.info("no volume spikes flagged in the current window")
        else:
            st.dataframe(anomalies, use_container_width=True, hide_index=True)

    except FileNotFoundError as e:
        st.warning(str(e))
        st.code(
            "pip install -r requirements.txt\n"
            "python -m src.extract\n"
            "dbt build --project-dir dbt_project --profiles-dir dbt_project\n"
            "streamlit run src/app.py"
        )
    except duckdb.CatalogException:
        st.warning("db file exists but marts aren't built — run dbt build")
    except duckdb.Error as e:
        st.error(f"duckdb blew up: {e}")
        log.exception("query failed")


if __name__ == "__main__":
    main()
