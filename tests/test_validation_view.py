from __future__ import annotations

from stock_ai.app.validation_view import (
    build_candidate_evidence,
    confidence_label,
    find_reproduced_conditions,
    summarize_conditions,
    summarize_historical_conditions,
)


def test_summarize_conditions_reports_evidence_and_results() -> None:
    events = [
        {
            "technical_conditions": '["出来高急増"]',
            "news_conditions": '["上方修正"]',
            "return_5d": "4.0",
        },
        {
            "technical_conditions": '["出来高急増"]',
            "news_conditions": '["上方修正"]',
            "return_5d": "-2.0",
        },
    ]

    result = summarize_conditions(events, horizon=5)
    upward = result[result["根拠条件"] == "上方修正"].iloc[0]

    assert upward["発生件数"] == 2
    assert upward["評価済み"] == 2
    assert upward["勝率(%)"] == 50.0
    assert upward["平均リターン(%)"] == 1.0
    assert upward["信頼度"] == "参考"


def test_candidate_evidence_uses_best_matching_condition() -> None:
    events = [
        {
            "technical_conditions": '["EMA20>EMA75"]',
            "news_conditions": '["上方修正"]',
            "return_5d": "1.0",
        },
        {
            "technical_conditions": "[]",
            "news_conditions": '["上方修正"]',
            "return_5d": "5.0",
        },
    ]
    summary = summarize_conditions(events, horizon=5)
    candidates = build_candidate_evidence(
        [
            {
                "ticker": "6501.T",
                "company": "日立製作所",
                "signal_score": 60,
                "signal_reason": ["EMA20>EMA75", "上方修正"],
            }
        ],
        summary,
    )

    assert candidates.iloc[0]["過去に最も強い根拠"] == "上方修正"
    assert candidates.iloc[0]["平均リターン(%)"] == 3.0


def test_confidence_thresholds_are_explicit() -> None:
    assert confidence_label(9) == "参考"
    assert confidence_label(10) == "蓄積中"
    assert confidence_label(30) == "検証可能"


def test_historical_conditions_use_backtest_reasons_and_net_return() -> None:
    events = [
        {
            "signal_reason": "EMA20>EMA75; MACDゴールデンクロス",
            "market_regime": "上昇",
            "return_5d": "3.0",
        },
        {
            "signal_reason": "EMA20>EMA75",
            "market_regime": "下落",
            "return_5d": "-1.0",
        },
    ]

    result = summarize_historical_conditions(events, horizon=5)
    ema = result[result["根拠条件"] == "EMA20>EMA75"].iloc[0]

    assert ema["評価済み"] == 2
    assert ema["勝率(%)"] == 50.0
    assert ema["平均リターン(%)"] == 1.0
    assert "市場環境：上昇" in result["根拠条件"].tolist()


def test_reproduced_conditions_require_positive_results_in_both_sets() -> None:
    historical = summarize_historical_conditions(
        [{"signal_reason": "EMA20>EMA75", "return_5d": "2.0"}],
        horizon=5,
    )
    forward = summarize_conditions(
        [
            {
                "technical_conditions": '["EMA20>EMA75"]',
                "news_conditions": "[]",
                "return_5d": "1.0",
            }
        ],
        horizon=5,
    )

    result = find_reproduced_conditions(historical, forward)

    assert result.iloc[0]["根拠条件"] == "EMA20>EMA75"
    assert result.iloc[0]["再現スコア"] == 3.0
