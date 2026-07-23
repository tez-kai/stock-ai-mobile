from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_ai.stocks.indicators import calculate_indicators


ChartWindow = pd.DataFrame


def load_chart_frame(stock_csv_path: str | Path) -> ChartWindow:
    """既存の data/raw/stocks/{ticker}.csv からチャート表示用データを読み込む。"""
    path = Path(stock_csv_path)
    if not path.exists():
        return pd.DataFrame()

    frame = pd.read_csv(path)
    if frame.empty:
        return pd.DataFrame()

    frame = frame.copy()
    if "Date" not in frame.columns:
        return pd.DataFrame()

    frame = frame.rename(columns=lambda column: str(column).strip())
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return frame


def ensure_indicator_columns(frame: ChartWindow) -> ChartWindow:
    """既存 CSV に指標列がなければ、既存の calculate_indicators 関数で補完する。"""
    if frame.empty:
        return frame.copy()

    required_columns = {"SMA5", "SMA25", "SMA75", "RSI14", "MACD", "MACD signal"}
    if required_columns.issubset(frame.columns):
        return frame.copy()

    enriched = calculate_indicators(frame.copy())
    return enriched


def filter_chart_window(frame: ChartWindow, window_label: str) -> ChartWindow:
    """表示期間に応じてデータを抽出する。"""
    if frame.empty:
        return frame.copy()

    if "Date" not in frame.columns:
        return frame.copy()

    normalized_frame = frame.copy()
    normalized_frame["Date"] = pd.to_datetime(normalized_frame["Date"], errors="coerce")
    normalized_frame = normalized_frame.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    if normalized_frame.empty:
        return normalized_frame.copy()

    days_map = {
        "1か月": 30,
        "3か月": 90,
        "6か月": 180,
        "1年": 365,
    }
    days = days_map.get(window_label, 365)
    latest = normalized_frame["Date"].iloc[-1]
    cutoff = latest - pd.Timedelta(days=days)
    return normalized_frame[normalized_frame["Date"] >= cutoff].copy().reset_index(drop=True)


def prepare_chart_frame(stock_csv_path: str | Path, window_label: str) -> ChartWindow:
    """表示前に指標計算を補完し、その後で期間を絞り込む。"""
    raw_frame = load_chart_frame(stock_csv_path)
    if raw_frame.empty:
        return raw_frame.copy()

    enriched_frame = ensure_indicator_columns(raw_frame)
    return filter_chart_window(enriched_frame, window_label)
