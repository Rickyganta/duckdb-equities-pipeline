import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from src.config import PERIOD, TICKERS

log = logging.getLogger(__name__)

RETRIES = 3
COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume", "extracted_at")

# yfinance breaks a lot lately; this endpoint still works with a browser UA
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def get_browser_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    return session


def _finalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    out = df.copy()
    out["symbol"] = symbol.upper().strip()
    out["extracted_at"] = datetime.utcnow()
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.tz_localize(None)

    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    cutoff = datetime.utcnow() - timedelta(days=30)
    out = out[out["date"] >= pd.Timestamp(cutoff)]
    out = out.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    out["volume"] = out["volume"].astype("int64")

    return out[list(COLUMNS)].copy()


def _clean_yfinance_frame(history: pd.DataFrame, symbol: str) -> pd.DataFrame:
    df = history.reset_index()
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    if "date" not in df.columns and "datetime" in df.columns:
        df = df.rename(columns={"datetime": "date"})
    return _finalize(df, symbol)


def fetch_ticker_chart_api(symbol: str, session: requests.Session) -> pd.DataFrame | None:
    url = CHART_URL.format(symbol=symbol)

    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(
                url,
                params={"range": "1mo", "interval": "1d"},
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()

            results = payload.get("chart", {}).get("result") or []
            if not results:
                log.warning("%s chart api returned empty result", symbol)
                continue

            block = results[0]
            quote = block["indicators"]["quote"][0]
            timestamps = block.get("timestamp") or []

            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(timestamps, unit="s", utc=True),
                    "open": quote.get("open"),
                    "high": quote.get("high"),
                    "low": quote.get("low"),
                    "close": quote.get("close"),
                    "volume": quote.get("volume"),
                }
            )
            cleaned = _finalize(frame, symbol)
            if cleaned.empty:
                log.warning("%s chart api had no rows after cleanup", symbol)
                continue

            log.info("chart api got %s rows for %s", len(cleaned), symbol)
            return cleaned

        except Exception as exc:
            log.warning("%s chart api attempt %s failed: %s", symbol, attempt, exc)
            if attempt < RETRIES:
                time.sleep(2 * attempt)

    return None


def fetch_ticker_yfinance(
    symbol: str, session: requests.Session, period: str = PERIOD
) -> pd.DataFrame | None:
    history = None

    for attempt in range(1, RETRIES + 1):
        try:
            history = yf.Ticker(symbol, session=session).history(period=period)
            if history is not None and not history.empty:
                cleaned = _clean_yfinance_frame(history, symbol)
                log.info("yfinance got %s rows for %s", len(cleaned), symbol)
                return cleaned
        except Exception as exc:
            log.warning("%s yfinance attempt %s failed: %s", symbol, attempt, exc)

        if attempt < RETRIES:
            time.sleep(2 * attempt)

    return None


def fetch_ticker(symbol: str, session: requests.Session, period: str = PERIOD) -> pd.DataFrame | None:
    log.info("fetching 30-day history for %s", symbol)

    # try yfinance first, fall back to chart api (more reliable lately)
    frame = fetch_ticker_yfinance(symbol, session, period)
    if frame is not None:
        return frame

    log.info("yfinance empty for %s — trying yahoo chart api", symbol)
    return fetch_ticker_chart_api(symbol, session)


def fetch_all(tickers: tuple[str, ...] = TICKERS) -> pd.DataFrame | None:
    session = get_browser_session()
    chunks = []
    failed = []

    for symbol in tickers:
        frame = fetch_ticker(symbol, session)
        if frame is None:
            failed.append(symbol)
        else:
            chunks.append(frame)

    if failed:
        log.error("failed symbols: %s", ", ".join(failed))

    if not chunks:
        return None

    return pd.concat(chunks, ignore_index=True)
