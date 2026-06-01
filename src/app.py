import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from sklearn.linear_model import LinearRegression

from src.config import DB_PATH, TICKERS

log = logging.getLogger(__name__)

INITIAL_CAPITAL = 10_000.0
FORECAST_DAYS = 7

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
    volume_anomaly_flag,
    extracted_at
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

CORE_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "daily_return_percentage",
    "sma_7",
    "sma_21",
    "rolling_volatility_30",
)

ENTERPRISE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    letter-spacing: -0.01em;
}

.block-container {
    padding-top: 1.25rem;
    padding-bottom: 1.25rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

h1, h2, h3 {
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

div[data-testid="stMetric"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 0.75rem 1rem;
}

div[data-testid="stMetric"] label {
    font-size: 0.78rem;
    font-weight: 500;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
    background: transparent;
}

.stTabs [data-baseweb="tab"] {
    height: 2.75rem;
    padding: 0 1.25rem;
    font-weight: 500;
    color: #475569;
    border-radius: 8px 8px 0 0;
}

.stTabs [aria-selected="true"] {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-bottom: 2px solid #ffffff;
}

section[data-testid="stSidebar"] {
    border-right: 1px solid #e2e8f0;
}

.telemetry-panel {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
}
</style>
"""


def inject_enterprise_css() -> None:
    st.markdown(ENTERPRISE_CSS, unsafe_allow_html=True)


@st.cache_resource
def connect(db_path: str):
    return duckdb.connect(db_path, read_only=True)


@st.cache_data(ttl=300)
def load_facts(db_path: str) -> pd.DataFrame:
    try:
        conn = connect(db_path)
        return conn.execute(FACT_SQL).fetchdf()
    except duckdb.Error:
        log.exception("failed to load facts")
        raise


@st.cache_data(ttl=300)
def load_anomalies(db_path: str) -> pd.DataFrame:
    try:
        conn = connect(db_path)
        return conn.execute(ANOMALY_SQL).fetchdf()
    except duckdb.Error:
        log.exception("failed to load anomalies")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_data_health(db_path: str) -> dict:
    conn = connect(db_path)
    row = conn.execute(
        """
        select
            count(*) as total_rows,
            count(distinct symbol) as symbol_count,
            max(extracted_at) as last_ingestion,
            min(date) as earliest_date,
            max(date) as latest_date
        from marts.fct_daily_prices
        """
    ).fetchone()

    null_counts = {}
    for col in CORE_COLUMNS:
        if col == "symbol":
            continue
        n = conn.execute(
            f"select count(*) from marts.fct_daily_prices where {col} is null"
        ).fetchone()[0]
        null_counts[col] = int(n)

    raw_rows = conn.execute(
        "select count(*) from raw_stock_data"
    ).fetchone()[0]

    return {
        "total_rows": int(row[0] or 0),
        "symbol_count": int(row[1] or 0),
        "last_ingestion": row[2],
        "earliest_date": row[3],
        "latest_date": row[4],
        "null_counts": null_counts,
        "raw_rows": int(raw_rows or 0),
    }


def get_warehouse_size_mb(db_path: str) -> float | None:
    try:
        return round(os.path.getsize(db_path) / (1024 * 1024), 2)
    except OSError:
        log.warning("could not read warehouse file size")
        return None


@st.cache_data(ttl=60)
def load_infrastructure_telemetry(db_path: str) -> dict | None:
    try:
        conn = connect(db_path)
        raw_count = int(
            conn.execute("select count(*) from raw_stock_data").fetchone()[0] or 0
        )
        fact_count = int(
            conn.execute("select count(*) from marts.fct_daily_prices").fetchone()[0] or 0
        )
        return {
            "warehouse_mb": get_warehouse_size_mb(db_path),
            "raw_rows": raw_count,
            "fact_rows": fact_count,
            "total_processed_rows": fact_count,
        }
    except duckdb.CatalogException:
        return None
    except duckdb.Error:
        log.exception("telemetry query failed")
        return None


def calc_max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    drawdown = (equity - peak) / peak.replace(0, np.nan)
    return float(drawdown.min() * 100)


def build_candlestick_chart(ticker_df: pd.DataFrame, symbol: str) -> go.Figure:
    df = ticker_df.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"])
    df["volume_color"] = np.where(df["close"] >= df["open"], "#26a69a", "#ef5350")

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

    if df["sma_7"].notna().any():
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

    if df["sma_21"].notna().any():
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


def run_sma_crossover_backtest(df: pd.DataFrame, initial: float = INITIAL_CAPITAL):
    data = df.sort_values("date").dropna(subset=["close", "sma_7"]).copy()
    if len(data) < 2:
        return None

    cash = initial
    shares = 0.0
    values = []
    trade_returns = []
    entry_price = None

    for _, row in data.iterrows():
        price = float(row["close"])
        sma = float(row["sma_7"])

        if price > sma and shares == 0 and cash > 0:
            shares = cash / price
            entry_price = price
            cash = 0.0
        elif price < sma and shares > 0 and entry_price is not None:
            trade_returns.append((price - entry_price) / entry_price * 100)
            cash = shares * price
            shares = 0.0
            entry_price = None

        values.append(cash + shares * price)

    equity = pd.Series(values, index=pd.to_datetime(data["date"]))
    final = float(equity.iloc[-1])
    wins = sum(1 for r in trade_returns if r > 0)
    win_rate = (wins / len(trade_returns) * 100) if trade_returns else 0.0

    return {
        "final_value": final,
        "net_pnl": final - initial,
        "return_pct": ((final / initial) - 1) * 100,
        "max_drawdown": calc_max_drawdown(equity),
        "win_rate": win_rate,
        "trade_count": len(trade_returns),
        "equity_curve": equity,
    }


def run_buy_and_hold(df: pd.DataFrame, initial: float = INITIAL_CAPITAL):
    data = df.sort_values("date").dropna(subset=["close"]).copy()
    if len(data) < 2:
        return None

    entry = float(data.iloc[0]["close"])
    exit_price = float(data.iloc[-1]["close"])
    if entry <= 0:
        return None

    shares = initial / entry
    final = shares * exit_price
    equity = shares * data["close"].astype(float)

    return {
        "final_value": final,
        "net_pnl": final - initial,
        "return_pct": ((final / initial) - 1) * 100,
        "equity_curve": pd.Series(equity.values, index=pd.to_datetime(data["date"])),
    }


def build_forecast(df: pd.DataFrame, days: int = FORECAST_DAYS):
    data = df.sort_values("date").dropna(subset=["close"]).copy()
    if len(data) < 5:
        return None

    data["date"] = pd.to_datetime(data["date"])
    y = data["close"].astype(float).values
    preds = None
    method = "linear regression"

    if len(data) >= 10:
        try:
            from statsmodels.tsa.ar_model import AutoReg

            lags = max(1, min(5, len(data) // 3))
            ar = AutoReg(y, lags=lags, old_names=False).fit()
            preds = ar.forecast(steps=days)
            method = f"AR({lags})"
        except Exception:
            log.warning("AR forecast failed — falling back to linear trend")

    if preds is None:
        try:
            x = np.arange(len(data)).reshape(-1, 1)
            model = LinearRegression()
            model.fit(x, y)
            future_x = np.arange(len(data), len(data) + days).reshape(-1, 1)
            preds = model.predict(future_x)
        except Exception:
            log.exception("linear forecast failed")
            return None

    last_date = data["date"].iloc[-1]
    future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=days)

    history = data[["date", "close"]].rename(columns={"close": "price"})
    history["series"] = "actual"

    forecast = pd.DataFrame(
        {"date": future_dates, "price": preds, "series": "forecast", "method": method}
    )

    return history, forecast, method


def build_forecast_chart(history: pd.DataFrame, forecast: pd.DataFrame, symbol: str, method: str):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history["date"],
            y=history["price"],
            mode="lines",
            name="historical close",
            line=dict(color="#1976d2", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast["date"],
            y=forecast["price"],
            mode="lines+markers",
            name="7-day forecast",
            line=dict(color="#e91e63", width=2, dash="dash"),
            marker=dict(size=6),
        )
    )
    fig.update_layout(
        title=f"{symbol} — {method} forecast",
        template="plotly_white",
        height=450,
        xaxis_title="date",
        yaxis_title="close price",
        hovermode="x unified",
    )
    return fig


def freshness_status(last_ingestion) -> tuple[str, str]:
    if last_ingestion is None or pd.isna(last_ingestion):
        return "unknown", "⚪"

    ts = pd.Timestamp(last_ingestion)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    age_hours = (pd.Timestamp.now(tz="UTC") - ts).total_seconds() / 3600

    if age_hours <= 24:
        return f"fresh ({age_hours:.1f}h ago)", "🟢"
    return f"stale ({age_hours:.1f}h ago)", "🔴"


def render_market_dashboard(ticker_df: pd.DataFrame, symbol: str, db_path: str):
    latest = ticker_df.sort_values("date").iloc[-1]
    daily_ret = latest["daily_return_percentage"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "close",
        f"${latest['close']:,.2f}",
        delta=round(float(daily_ret), 2) if pd.notna(daily_ret) else None,
        delta_color="normal",
        help="intraday return % (close vs open)",
    )
    c2.metric(
        "sma_7",
        f"${latest['sma_7']:,.2f}" if pd.notna(latest["sma_7"]) else "n/a",
    )
    c3.metric(
        "sma_21",
        f"${latest['sma_21']:,.2f}" if pd.notna(latest["sma_21"]) else "n/a",
    )
    c4.metric(
        "volatility (30d)",
        f"{latest['rolling_volatility_30']:.2f}"
        if pd.notna(latest["rolling_volatility_30"])
        else "n/a",
    )

    st.plotly_chart(
        build_candlestick_chart(ticker_df, symbol),
        use_container_width=True,
    )

    st.subheader("volume anomalies")
    st.caption("days where volume > 2x the 30-day rolling average")
    try:
        anomalies = load_anomalies(db_path)
    except duckdb.Error:
        st.warning("could not load anomaly data — database may be locked")
        return

    symbol_anomalies = anomalies[anomalies["symbol"] == symbol] if not anomalies.empty else anomalies
    if symbol_anomalies.empty:
        st.info("no volume spikes flagged for this ticker")
    else:
        st.dataframe(symbol_anomalies, use_container_width=True, hide_index=True)


def render_backtester(ticker_df: pd.DataFrame, symbol: str):
    st.subheader("sma crossover backtest")
    st.caption("buy when close > sma_7 · sell when close < sma_7 · compare vs buy & hold")

    capital = st.number_input(
        "starting capital ($)",
        min_value=1000.0,
        max_value=1_000_000.0,
        value=INITIAL_CAPITAL,
        step=1000.0,
    )

    strategy = run_sma_crossover_backtest(ticker_df, capital)
    baseline = run_buy_and_hold(ticker_df, capital)

    if strategy is None or baseline is None:
        st.warning("not enough clean data to run a backtest for this ticker")
        return

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("strategy ROI", f"{strategy['return_pct']:+.2f}%")
    r1c2.metric("strategy final value", f"${strategy['final_value']:,.2f}")
    r1c3.metric("strategy p/l", f"${strategy['net_pnl']:+,.2f}")
    r1c4.metric(
        "alpha vs buy & hold",
        f"${strategy['final_value'] - baseline['final_value']:+,.2f}",
    )

    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("max drawdown", f"{strategy['max_drawdown']:.2f}%")
    r2c2.metric(
        "win rate",
        f"{strategy['win_rate']:.1f}%"
        if strategy["trade_count"] > 0
        else "n/a",
    )
    r2c3.metric("completed trades", strategy["trade_count"])
    r2c4.metric("buy & hold ROI", f"{baseline['return_pct']:+.2f}%")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=strategy["equity_curve"].index,
            y=strategy["equity_curve"].values,
            name="sma crossover",
            line=dict(color="#2196f3", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=baseline["equity_curve"].index,
            y=baseline["equity_curve"].values,
            name="buy & hold",
            line=dict(color="#9e9e9e", width=2, dash="dot"),
        )
    )
    fig.update_layout(
        title=f"{symbol} — equity curve comparison",
        template="plotly_white",
        height=400,
        xaxis_title="date",
        yaxis_title="portfolio value ($)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_forecasting(ticker_df: pd.DataFrame, symbol: str):
    st.subheader("7-day price forecast")
    st.caption("AR model when enough history, otherwise linear trend regression")

    result = build_forecast(ticker_df)
    if result is None:
        st.warning("need at least 5 trading days with valid close prices to forecast")
        return

    history, forecast, method = result
    st.plotly_chart(
        build_forecast_chart(history, forecast, symbol, method),
        use_container_width=True,
    )

    st.dataframe(
        forecast.rename(columns={"price": "forecast_close"}),
        use_container_width=True,
        hide_index=True,
    )


def render_data_quality(db_path: str):
    st.subheader("data health scorecard")

    try:
        health = load_data_health(db_path)
    except duckdb.CatalogException:
        st.warning("mart tables missing — run dbt build first")
        return
    except duckdb.Error:
        st.warning("database temporarily locked or unavailable — try again in a moment")
        return

    status, icon = freshness_status(health["last_ingestion"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("fact rows", f"{health['total_rows']:,}")
    c2.metric("raw rows", f"{health['raw_rows']:,}")
    c3.metric("symbols tracked", health["symbol_count"])
    c4.metric("freshness", f"{icon} {status}")

    if health["last_ingestion"] is not None:
        st.write(
            f"**last ingestion:** {pd.Timestamp(health['last_ingestion']).strftime('%Y-%m-%d %H:%M UTC')}"
        )
    if health["earliest_date"] and health["latest_date"]:
        st.write(
            f"**date range:** {health['earliest_date']} → {health['latest_date']}"
        )

    st.markdown("---")
    st.subheader("Infrastructure Telemetry & Storage Volume")

    telemetry = load_infrastructure_telemetry(db_path)
    if telemetry is None:
        st.warning("telemetry unavailable — warehouse tables may not exist yet")
    else:
        t1, t2, t3, t4 = st.columns(4)
        size_mb = telemetry["warehouse_mb"]
        t1.metric(
            "warehouse size (MB)",
            f"{size_mb:.2f}" if size_mb is not None else "n/a",
        )
        t2.metric(
            "total processed rows",
            f"{telemetry['total_processed_rows']:,}",
        )
        t3.metric("raw_stock_data rows", f"{telemetry['raw_rows']:,}")
        t4.metric("fct_daily_prices rows", f"{telemetry['fact_rows']:,}")

    st.subheader("null-value audit")
    audit = pd.DataFrame(
        [
            {"column": col, "null_count": n, "status": "ok" if n == 0 else "review"}
            for col, n in health["null_counts"].items()
        ]
    )
    st.dataframe(audit, use_container_width=True, hide_index=True)

    total_nulls = audit["null_count"].sum()
    if total_nulls == 0:
        st.success("all core metric columns are fully populated")
    else:
        st.warning(f"{total_nulls} total nulls across core columns — review upstream extract/dbt")


def main():
    st.set_page_config(page_title="Equities Lakehouse", layout="wide")
    inject_enterprise_css()
    st.title("Equities Analytics Lakehouse")
    st.caption("duckdb · dbt incremental marts · streamlit analytics")

    try:
        if not DB_PATH.exists():
            raise FileNotFoundError(
                "no warehouse.duckdb yet — run extract + dbt first"
            )

        try:
            facts = load_facts(str(DB_PATH))
        except duckdb.Error:
            st.warning("warehouse is locked or unavailable — close other connections and retry")
            return

        if facts.empty:
            st.warning("fact table is empty")
            return

        selected = st.sidebar.selectbox("ticker", list(TICKERS), index=0)
        ticker_df = facts[facts["symbol"] == selected].copy()

        tab_dash, tab_back, tab_fore, tab_ops = st.tabs(
            [
                "Market Dashboard",
                "Algorithmic Backtester",
                "Predictive Forecasting",
                "Data Quality Ops",
            ]
        )

        with tab_dash:
            if ticker_df.empty:
                st.warning(f"no rows for {selected}")
            else:
                render_market_dashboard(ticker_df, selected, str(DB_PATH))

        with tab_back:
            if ticker_df.empty:
                st.warning(f"no rows for {selected}")
            else:
                render_backtester(ticker_df, selected)

        with tab_fore:
            if ticker_df.empty:
                st.warning(f"no rows for {selected}")
            else:
                render_forecasting(ticker_df, selected)

        with tab_ops:
            render_data_quality(str(DB_PATH))

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
    except Exception as e:
        st.error(f"something broke: {e}")
        log.exception("unexpected dashboard error")


if __name__ == "__main__":
    main()
