from __future__ import annotations

import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """株価データから主要なテクニカル指標を計算する。"""
    result = df.copy()

    if result.empty:
        return result

    result["SMA5"] = result["Close"].rolling(window=5, min_periods=1).mean()
    result["SMA25"] = result["Close"].rolling(window=25, min_periods=1).mean()
    result["SMA75"] = result["Close"].rolling(window=75, min_periods=1).mean()

    close = result["Close"].astype(float)
    result["EMA20"] = close.ewm(span=20, adjust=False).mean()
    result["EMA75"] = close.ewm(span=75, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=14, min_periods=14).mean()
    avg_loss = loss.rolling(window=14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    result["RSI14"] = pd.to_numeric(100 - (100 / (1 + rs)), errors="coerce")
    result["RSI14"] = result["RSI14"].fillna(50)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    result["MACD"] = ema12 - ema26
    result["MACD signal"] = result["MACD"].ewm(span=9, adjust=False).mean()

    result["Volume Avg 20"] = result["Volume"].rolling(window=20, min_periods=1).mean()
    result["Volume Ratio"] = result["Volume"] / result["Volume Avg 20"].replace(0, pd.NA)
    result["Volume Ratio"] = result["Volume Ratio"].fillna(0)

    result["High 20"] = result["High"].rolling(window=20, min_periods=1).max()
    # 当日高値を含めず、前日までの20日高値をブレイク判定に使う。
    result["Prior High 20"] = result["High"].shift(1).rolling(window=20, min_periods=20).max()
    result["Low 20"] = result["Low"].rolling(window=20, min_periods=1).min()
    result["Return 20"] = result["Close"].pct_change(20, fill_method=None).fillna(0)

    tr = pd.concat(
        [
            (result["High"] - result["Low"]).abs(),
            (result["High"] - result["Close"].shift(1)).abs(),
            (result["Low"] - result["Close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["ATR14"] = tr.rolling(window=14, min_periods=1).mean()
    result["ATR Percent"] = (result["ATR14"] / close.replace(0, pd.NA) * 100).fillna(0)

    return result
