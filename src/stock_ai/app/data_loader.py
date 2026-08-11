from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DashboardSnapshot:
    last_updated: str = ""
    news_count: int = 0
    related_tickers: list[str] = field(default_factory=list)
    analysis_tickers: list[str] = field(default_factory=list)
    rankings: list[dict[str, Any]] = field(default_factory=list)
    signal_history: list[dict[str, Any]] = field(default_factory=list)
    backtest_summary: dict[str, Any] = field(default_factory=dict)
    backtest_events: list[dict[str, Any]] = field(default_factory=list)
    backtest_by_ticker: list[dict[str, Any]] = field(default_factory=list)
    backtest_by_reason: list[dict[str, Any]] = field(default_factory=list)
    backtest_by_combination: list[dict[str, Any]] = field(default_factory=list)
    backtest_by_market_regime: list[dict[str, Any]] = field(default_factory=list)
    backtest_by_time_split: list[dict[str, Any]] = field(default_factory=list)
    backtest_robustness: dict[str, Any] = field(default_factory=dict)
    backtest_exit_strategies: list[dict[str, Any]] = field(default_factory=list)
    backtest_exit_strategy_stability: list[dict[str, Any]] = field(default_factory=list)
    portfolio_backtest: list[dict[str, Any]] = field(default_factory=list)
    portfolio_backtest_summary: dict[str, Any] = field(default_factory=dict)
    validation_events: list[dict[str, Any]] = field(default_factory=list)
    strategy_performance: list[dict[str, Any]] = field(default_factory=list)
    strategy_status_assessments: list[dict[str, Any]] = field(default_factory=list)
    error_message: str = ""


def _normalize_reason(reason: Any) -> str:
    if isinstance(reason, list):
        return "; ".join(str(item) for item in reason)
    if reason is None:
        return ""
    return str(reason)


def _load_ranking_rows(ranking_json_path: Path, ranking_csv_path: Path) -> list[dict[str, Any]]:
    if ranking_json_path.exists():
        with ranking_json_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, list):
            rows = payload
        else:
            rows = []
    elif ranking_csv_path.exists():
        rows = []
        with ranking_csv_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                rows.append(
                    {
                        "ticker": row.get("ticker", ""),
                        "company": row.get("company", ""),
                        "signal_score": int(row.get("signal_score", 0) or 0),
                        "technical_score": int(row.get("technical_score", 0) or 0),
                        "news_score": int(row.get("news_score", 0) or 0),
                        "total_score": int(row.get("total_score", row.get("signal_score", 0)) or 0),
                        "related_news_count": int(row.get("related_news_count", 0) or 0),
                        "latest_news_published": row.get("latest_news_published", ""),
                        "strongest_match_type": row.get("strongest_match_type", ""),
                        "news_count_score": int(row.get("news_count_score", 0) or 0),
                        "news_freshness_score": int(row.get("news_freshness_score", 0) or 0),
                        "news_match_score": int(row.get("news_match_score", 0) or 0),
                        "atr_percent": float(row.get("atr_percent", 0) or 0),
                        "risk_level": row.get("risk_level", ""),
                        "signal_reason": row.get("signal_reason", ""),
                    }
                )
    else:
        rows = []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            {
                "ticker": str(row.get("ticker", "")),
                "company": str(row.get("company", "")),
                "signal_score": int(row.get("signal_score", 0) or 0),
                "technical_score": int(row.get("technical_score", 0) or 0),
                "news_score": int(row.get("news_score", 0) or 0),
                "total_score": int(row.get("total_score", row.get("signal_score", 0)) or 0),
                "related_news_count": int(row.get("related_news_count", 0) or 0),
                "latest_news_published": str(row.get("latest_news_published", "")),
                "strongest_match_type": str(row.get("strongest_match_type", "")),
                "news_count_score": int(row.get("news_count_score", 0) or 0),
                "news_freshness_score": int(row.get("news_freshness_score", 0) or 0),
                "news_match_score": int(row.get("news_match_score", 0) or 0),
                "atr_percent": float(row.get("atr_percent", 0) or 0),
                "risk_level": str(row.get("risk_level", "")),
                "signal_reason": _normalize_reason(row.get("signal_reason", "")),
            }
        )
    return normalized_rows


def load_dashboard_snapshot(processed_dir: Path | str = "data/processed") -> DashboardSnapshot:
    """Streamlit ダッシュボードが表示するためのデータを読み込む。"""
    root_dir = Path(processed_dir)
    summary_path = root_dir / "summary.json"
    ranking_json_path = root_dir / "ranking.json"
    ranking_csv_path = root_dir / "ranking.csv"
    history_path = root_dir / "signal_history.csv"
    backtest_summary_path = root_dir / "backtest_summary.json"
    backtest_events_path = root_dir / "backtest_events.csv"
    detail_paths = {
        "backtest_by_ticker": root_dir / "backtest_by_ticker.csv",
        "backtest_by_reason": root_dir / "backtest_by_reason.csv",
        "backtest_by_combination": root_dir / "backtest_by_combination.csv",
        "backtest_by_market_regime": root_dir / "backtest_by_market_regime.csv",
        "backtest_by_time_split": root_dir / "backtest_by_time_split.csv",
    }

    snapshot = DashboardSnapshot(error_message="")

    if not summary_path.exists() or not ranking_json_path.exists() and not ranking_csv_path.exists():
        snapshot.error_message = (
            "分析データが見つかりません。まずローカルで `python -m stock_ai.main` を実行して、"
            "`data/processed` 配下に `summary.json` と `ranking.json` / `ranking.csv` を作成してください。"
        )
        return snapshot

    summary_payload: dict[str, Any] = {}
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8") as file:
            summary_payload = json.load(file)

    snapshot.news_count = int(summary_payload.get("news_count", 0) or 0)
    snapshot.related_tickers = [str(item) for item in summary_payload.get("related_tickers", [])]
    snapshot.analysis_tickers = [str(item) for item in summary_payload.get("analysis_tickers", snapshot.related_tickers)]
    snapshot.rankings = _load_ranking_rows(ranking_json_path, ranking_csv_path)
    if history_path.exists():
        with history_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.signal_history = list(csv.DictReader(file))
    if backtest_summary_path.exists():
        with backtest_summary_path.open("r", encoding="utf-8") as file:
            snapshot.backtest_summary = json.load(file)
    if backtest_events_path.exists():
        with backtest_events_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.backtest_events = list(csv.DictReader(file))
    for attribute, detail_path in detail_paths.items():
        if detail_path.exists():
            with detail_path.open("r", encoding="utf-8-sig", newline="") as file:
                setattr(snapshot, attribute, list(csv.DictReader(file)))
    robustness_path = root_dir / "backtest_robustness.json"
    if robustness_path.exists():
        with robustness_path.open("r", encoding="utf-8") as file:
            snapshot.backtest_robustness = json.load(file)
    exit_strategy_path = root_dir / "backtest_exit_strategies.csv"
    if exit_strategy_path.exists():
        with exit_strategy_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.backtest_exit_strategies = list(csv.DictReader(file))
    stability_path = root_dir / "backtest_exit_strategy_stability.csv"
    if stability_path.exists():
        with stability_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.backtest_exit_strategy_stability = list(csv.DictReader(file))
    portfolio_path = root_dir / "portfolio_backtest.csv"
    if portfolio_path.exists():
        with portfolio_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.portfolio_backtest = list(csv.DictReader(file))
    portfolio_summary_path = root_dir / "portfolio_backtest_summary.json"
    if portfolio_summary_path.exists():
        with portfolio_summary_path.open("r", encoding="utf-8") as file:
            snapshot.portfolio_backtest_summary = json.load(file)
    validation_events_path = root_dir / "validation_events.csv"
    if validation_events_path.exists():
        with validation_events_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.validation_events = list(csv.DictReader(file))
    strategy_performance_path = root_dir / "strategy_performance.csv"
    if strategy_performance_path.exists():
        with strategy_performance_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.strategy_performance = list(csv.DictReader(file))
    strategy_status_path = root_dir / "strategy_status_assessment.csv"
    if strategy_status_path.exists():
        with strategy_status_path.open("r", encoding="utf-8-sig", newline="") as file:
            snapshot.strategy_status_assessments = list(csv.DictReader(file))

    latest_timestamp = 0.0
    for file_path in (
        summary_path,
        ranking_json_path,
        ranking_csv_path,
        history_path,
        backtest_summary_path,
        backtest_events_path,
        validation_events_path,
        strategy_performance_path,
        strategy_status_path,
    ):
        if file_path.exists():
            latest_timestamp = max(latest_timestamp, file_path.stat().st_mtime)

    if latest_timestamp:
        snapshot.last_updated = datetime.fromtimestamp(latest_timestamp, tz=timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    return snapshot
