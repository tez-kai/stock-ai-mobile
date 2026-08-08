from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from stock_ai.app.intraday_paper_view import (
    build_activity_feed,
    build_feedback_issue_url,
    build_position_summary,
    build_trade_history,
    build_transaction_ledger,
    execution_quality,
)


def _sample_state() -> dict[str, object]:
    return {
        "closed_trades": [
            {
                "ticker": "6501.T",
                "company": "日立製作所",
                "entry_at": "2026-08-01T00:05:00+00:00",
                "entry_price": 4_000,
                "entry_fee": 100,
                "entry_amount": 80_100,
                "exit_at": "2026-08-01T05:05:00+00:00",
                "exit_price": 4_100,
                "exit_fee": 100,
                "exit_amount": 81_900,
                "shares": 20,
                "net_pnl": 1_800,
                "return_percent": 2.25,
                "holding_minutes": 300,
                "signal_reason": ["出来高2倍以上"],
                "exit_reason": "利確",
            }
        ],
        "positions": [
            {
                "ticker": "7011.T",
                "company": "三菱重工業",
                "entry_at": "2026-08-02T00:05:00+00:00",
                "entry_price": 3_000,
                "entry_fee": 100,
                "entry_amount": 60_100,
                "shares": 20,
                "signal_reason": ["ニュース鮮度+20"],
            }
        ],
        "events": [
            {"status": "executed", "execution_delay_minutes": 6},
            {"status": "executed", "execution_delay_minutes": 9},
            {"status": "executed", "execution_delay_minutes": 120},
            {"status": "pending", "execution_delay_minutes": 5},
        ],
    }


def test_transaction_ledger_explains_cash_history() -> None:
    ledger = build_transaction_ledger(_sample_state())

    assert ledger["売買"].tolist() == ["買付", "売却", "買付"]
    assert ledger["受渡金額(円)"].tolist() == [-80_100, 81_900, -60_100]
    assert ledger["現金残高(円)"].tolist() == [419_900, 501_800, 441_700]
    assert ledger.iloc[1]["損益(円)"] == 1_800


def test_trade_history_keeps_entry_exit_and_result_together() -> None:
    history = build_trade_history(_sample_state())

    assert len(history) == 1
    assert history.iloc[0]["企業名"] == "日立製作所"
    assert history.iloc[0]["買付総額"] == 80_100
    assert history.iloc[0]["売却総額"] == 81_900
    assert history.iloc[0]["損益"] == 1_800
    assert history.iloc[0]["保有時間"] == "5.0時間"


def test_execution_quality_detects_late_legacy_fills() -> None:
    quality = execution_quality(_sample_state())

    assert quality == {
        "count": 3.0,
        "median": 9.0,
        "within_10": 66.7,
        "over_60": 1.0,
    }


def test_feedback_url_contains_user_observation() -> None:
    url = build_feedback_issue_url(
        "6501.T 日立製作所", "悪かった", ["買うのが遅い"], "価格を確認したい"
    )
    query = parse_qs(urlparse(url).query)

    assert url.startswith("https://github.com/tez-kai/stock-ai/issues/new?")
    assert "悪かった" in query["title"][0]
    assert "買うのが遅い" in query["body"][0]
    assert "価格を確認したい" in query["body"][0]


def test_position_summary_shows_money_and_reason_without_internal_ids() -> None:
    state = _sample_state()
    state["positions"][0]["latest_price"] = 3_100

    positions = build_position_summary(state)

    assert positions.iloc[0]["銘柄"] == "三菱重工業 (7011.T)"
    assert positions.iloc[0]["買付金額"] == 60_100
    assert positions.iloc[0]["現在評価額"] == 62_000
    assert positions.iloc[0]["含み損益"] == 1_900
    assert "order_id" not in positions.columns


def test_activity_feed_humanizes_internal_event_fields() -> None:
    state = _sample_state()
    state["events"] = [
        {
            "order_id": "buy:6501.T:internal",
            "side": "buy",
            "ticker": "6501.T",
            "company": "日立製作所",
            "signal_at": "2026-08-01T00:00:00+00:00",
            "executed_at": "2026-08-01T00:06:00+00:00",
            "execution_price": 4_000,
            "execution_delay_minutes": 6,
            "status": "executed",
            "signal_reason": ["出来高2倍以上"],
        }
    ]

    activity = build_activity_feed(state)

    assert activity.iloc[0]["行動"] == "買付"
    assert activity.iloc[0]["状態"] == "約定済み"
    assert activity.iloc[0]["シグナル→実行"] == "6分"
    assert "order_id" not in activity.columns
    assert "execute_after" not in activity.columns
