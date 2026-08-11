import pandas as pd

from stock_ai.app.strategy_monitor_view import build_monitor_rows, select_primary_assessment


def _row(dataset: str, status: str, days: int = 5):
    return {
        "strategy_id": "STR-000001", "strategy_version": "1",
        "dataset_type": dataset, "holding_period_days": str(days),
        "recommended_status": status, "stop_candidate": "False",
        "sample_size": "28", "expectancy": "0.5",
        "recent_50_expectancy": "0.5", "profit_factor": "1.2",
        "max_drawdown": "-12", "win_rate": "53.5",
        "assessment_reasons": "サンプル不足",
    }


def test_build_monitor_rows_translates_status_and_dataset():
    frame = build_monitor_rows([_row("PAPER", "FORWARD_TEST")])
    assert frame.iloc[0]["検証データ"] == "実運用"
    assert frame.iloc[0]["推奨状態"] == "実運用検証中"
    assert frame.iloc[0]["期待値(%)"] == 0.5


def test_primary_assessment_prefers_paper_five_day():
    frame = build_monitor_rows([
        _row("BACKTEST", "WARNING"),
        _row("PAPER", "FORWARD_TEST"),
        _row("PAPER", "FORWARD_TEST", days=20),
    ])
    selected = select_primary_assessment(frame)
    assert selected is not None
    assert selected["検証データ"] == "実運用"
    assert selected["保有日数"] == 5


def test_empty_rows_are_safe():
    frame = build_monitor_rows([])
    assert frame.empty
    assert select_primary_assessment(pd.DataFrame()) is None
