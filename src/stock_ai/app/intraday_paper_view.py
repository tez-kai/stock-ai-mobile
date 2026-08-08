from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


INITIAL_CAPITAL = 500_000.0
FEEDBACK_ISSUE_URL = "https://github.com/tez-kai/stock-ai/issues/new"


def _number(value: object, default: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    return default if pd.isna(parsed) else float(parsed)


def _format_time(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "—"
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("Asia/Tokyo")
    return parsed.strftime("%m/%d %H:%M")


def _reason_text(value: object) -> str:
    if isinstance(value, list):
        return " / ".join(str(item) for item in value)
    return str(value or "—")


def build_transaction_ledger(state: dict[str, object]) -> pd.DataFrame:
    """Create a chronological buy/sell cash ledger from open and closed trades."""
    transactions: list[dict[str, object]] = []
    all_trades = list(state.get("closed_trades", [])) + list(state.get("positions", []))
    for trade in all_trades:
        shares = int(_number(trade.get("shares")))
        entry_price = _number(trade.get("entry_price"))
        entry_fee = _number(trade.get("entry_fee"))
        entry_amount = _number(
            trade.get("entry_amount"), shares * entry_price + entry_fee
        )
        transactions.append(
            {
                "日時": trade.get("entry_at"),
                "売買": "買付",
                "ticker": trade.get("ticker", ""),
                "企業名": trade.get("company", trade.get("ticker", "")),
                "株数": shares,
                "価格(円)": entry_price,
                "手数料(円)": entry_fee,
                "受渡金額(円)": -entry_amount,
                "損益(円)": None,
                "根拠": _reason_text(trade.get("signal_reason")),
            }
        )
        if trade.get("exit_at"):
            exit_price = _number(trade.get("exit_price"))
            exit_fee = _number(trade.get("exit_fee"))
            exit_amount = _number(
                trade.get("exit_amount"), shares * exit_price - exit_fee
            )
            transactions.append(
                {
                    "日時": trade.get("exit_at"),
                    "売買": "売却",
                    "ticker": trade.get("ticker", ""),
                    "企業名": trade.get("company", trade.get("ticker", "")),
                    "株数": shares,
                    "価格(円)": exit_price,
                    "手数料(円)": exit_fee,
                    "受渡金額(円)": exit_amount,
                    "損益(円)": _number(trade.get("net_pnl")),
                    "根拠": _reason_text(trade.get("exit_reason")),
                }
            )
    if not transactions:
        return pd.DataFrame()
    frame = pd.DataFrame(transactions)
    frame["_time"] = pd.to_datetime(frame["日時"], errors="coerce", utc=True)
    frame = frame.sort_values("_time").reset_index(drop=True)
    frame["現金残高(円)"] = (
        INITIAL_CAPITAL + pd.to_numeric(frame["受渡金額(円)"], errors="coerce").fillna(0).cumsum()
    ).round(0)
    frame["日時"] = frame["日時"].map(_format_time)
    return frame.drop(columns="_time")


def build_trade_history(state: dict[str, object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade in state.get("closed_trades", []):
        shares = int(_number(trade.get("shares")))
        entry_price = _number(trade.get("entry_price"))
        exit_price = _number(trade.get("exit_price"))
        rows.append(
            {
                "企業名": trade.get("company", trade.get("ticker", "")),
                "ticker": trade.get("ticker", ""),
                "買付日時": _format_time(trade.get("entry_at")),
                "買値": entry_price,
                "売却日時": _format_time(trade.get("exit_at")),
                "売値": exit_price,
                "株数": shares,
                "買付総額": round(
                    _number(
                        trade.get("entry_amount"),
                        shares * entry_price + _number(trade.get("entry_fee")),
                    )
                ),
                "売却総額": round(
                    _number(
                        trade.get("exit_amount"),
                        shares * exit_price - _number(trade.get("exit_fee")),
                    )
                ),
                "損益": round(_number(trade.get("net_pnl"))),
                "収益率(%)": round(_number(trade.get("return_percent")), 2),
                "保有時間": _format_duration(trade),
                "買付根拠": _reason_text(trade.get("signal_reason")),
                "売却根拠": _reason_text(trade.get("exit_reason")),
            }
        )
    return pd.DataFrame(rows).sort_values("売却日時", ascending=False) if rows else pd.DataFrame()


def _format_duration(trade: dict[str, object]) -> str:
    minutes = _number(trade.get("holding_minutes"), -1)
    if minutes < 0:
        entry = pd.to_datetime(trade.get("entry_at"), errors="coerce", utc=True)
        exit_at = pd.to_datetime(trade.get("exit_at"), errors="coerce", utc=True)
        if pd.isna(entry) or pd.isna(exit_at):
            return "—"
        minutes = (exit_at - entry).total_seconds() / 60
    if minutes >= 1440:
        return f"{minutes / 1440:.1f}日"
    if minutes >= 60:
        return f"{minutes / 60:.1f}時間"
    return f"{minutes:.0f}分"


def execution_quality(state: dict[str, object]) -> dict[str, float]:
    delays = [
        _number(event.get("execution_delay_minutes"), -1)
        for event in state.get("events", [])
        if event.get("status") == "executed"
    ]
    delays = [value for value in delays if value >= 0]
    if not delays:
        return {"count": 0, "median": 0, "within_10": 0, "over_60": 0}
    series = pd.Series(delays)
    return {
        "count": float(len(delays)),
        "median": round(float(series.median()), 1),
        "within_10": round(float((series <= 10).mean() * 100), 1),
        "over_60": float((series > 60).sum()),
    }


def build_feedback_issue_url(
    target: str, rating: str, categories: list[str], note: str
) -> str:
    title = f"[運用フィードバック] {rating} - {target}"
    body = "\n".join(
        [
            "## 対象",
            target,
            "",
            "## 評価",
            rating,
            "",
            "## 分類",
            ", ".join(categories) if categories else "未分類",
            "",
            "## コメント",
            note or "（コメントなし）",
            "",
            "> スマホ版ダッシュボードから送信",
        ]
    )
    return f"{FEEDBACK_ISSUE_URL}?{urlencode({'title': title, 'body': body})}"


def _render_equity_chart(curve: pd.DataFrame) -> None:
    chart = curve.copy()
    chart["timestamp"] = pd.to_datetime(chart["timestamp"], errors="coerce")
    chart = chart.dropna(subset=["timestamp"])
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=chart["timestamp"], y=chart["total_assets"],
            name="総資産", mode="lines+markers", line={"width": 3, "color": "#1769aa"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=chart["timestamp"], y=chart["cash"],
            name="現金", mode="lines", line={"width": 1.5, "color": "#2e7d32"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=chart["timestamp"], y=chart["market_value"],
            name="保有株評価額", mode="lines", line={"width": 1.5, "color": "#ef6c00"},
        )
    )
    figure.add_hline(
        y=INITIAL_CAPITAL, line_dash="dot", line_color="#777",
        annotation_text="開始 50万円",
    )
    figure.update_layout(
        height=390, margin={"l": 10, "r": 10, "t": 30, "b": 10},
        yaxis_title="円", xaxis_title=None, hovermode="x unified",
        legend={"orientation": "h", "y": 1.12},
    )
    st.plotly_chart(figure, width="stretch")


def _render_positions(state: dict[str, object]) -> None:
    positions = state.get("positions", [])
    pending = state.get("pending_orders", [])
    if positions:
        rows = []
        for item in positions:
            shares = int(_number(item.get("shares")))
            entry_price = _number(item.get("entry_price"))
            latest_price = _number(item.get("latest_price"), entry_price)
            entry_cost = _number(
                item.get("entry_amount"),
                shares * entry_price + _number(item.get("entry_fee")),
            )
            market_value = shares * latest_price
            rows.append(
                {
                    "企業名": item.get("company", item.get("ticker", "")),
                    "ticker": item.get("ticker", ""),
                    "買付日時": _format_time(item.get("entry_at")),
                    "買値": entry_price,
                    "現在値": latest_price,
                    "株数": shares,
                    "買付総額": round(entry_cost),
                    "現在評価額": round(market_value),
                    "含み損益": round(market_value - entry_cost),
                    "含み損益率(%)": round((market_value / entry_cost - 1) * 100, 2)
                    if entry_cost else 0,
                    "根拠": _reason_text(item.get("signal_reason")),
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("現在の保有銘柄はありません。")
    if pending:
        st.markdown("#### 約定待ち")
        pending_rows = [
            {
                "売買": "買付" if item.get("side") == "buy" else "売却",
                "企業名": item.get("company", item.get("ticker", "")),
                "ticker": item.get("ticker", ""),
                "シグナル時刻": _format_time(item.get("signal_at")),
                "約定目標": _format_time(item.get("execute_after")),
                "状態": item.get("status", ""),
            }
            for item in pending
        ]
        st.dataframe(pd.DataFrame(pending_rows), width="stretch", hide_index=True)


def _render_feedback(state: dict[str, object]) -> None:
    st.caption("判断根拠・結果・画面の問題を残します。保存先は非公開のstock-ai課題一覧です。")
    choices = {"運用全体・画面": "運用全体・画面"}
    for trade in reversed(state.get("closed_trades", [])):
        label = (
            f"{trade.get('ticker')} {trade.get('company')} | "
            f"{_format_time(trade.get('entry_at'))}→{_format_time(trade.get('exit_at'))} | "
            f"{_number(trade.get('net_pnl')):+,.0f}円"
        )
        choices[label] = label
    with st.form("intraday_feedback"):
        selected = st.selectbox("対象", list(choices))
        rating = st.radio(
            "評価", ["良かった", "悪かった", "判断保留"], horizontal=True
        )
        categories = st.multiselect(
            "気になった点",
            [
                "根拠が妥当", "根拠が弱い", "買うのが遅い", "売るのが遅い",
                "価格が違う", "損失が大きい", "利益を伸ばせた", "画面が見づらい",
            ],
        )
        note = st.text_area("コメント", placeholder="何が良く、何を直すべきか")
        submitted = st.form_submit_button("フィードバックを作成", type="primary")
    if submitted:
        st.session_state["feedback_issue_url"] = build_feedback_issue_url(
            selected, rating, categories, note
        )
        st.session_state["feedback_download"] = pd.DataFrame(
            [{"対象": selected, "評価": rating, "分類": " / ".join(categories), "コメント": note}]
        ).to_csv(index=False).encode("utf-8-sig")
    if st.session_state.get("feedback_issue_url"):
        st.success("内容を作成しました。次のボタンでGitHubを開き、最後に『Submit new issue』を押すと保存されます。")
        st.link_button(
            "フィードバックを保存（GitHub）",
            st.session_state["feedback_issue_url"],
            type="primary",
        )
        st.download_button(
            "CSVでも保存",
            st.session_state["feedback_download"],
            file_name="stock_ai_feedback.csv",
            mime="text/csv",
        )


def render_intraday_paper_view(processed_dir: Path) -> None:
    state_path = processed_dir / "intraday_paper_portfolio.json"
    st.subheader("50万円の検証運用")
    st.caption(
        "いつ、何を、いくらで買い、売り、その結果50万円がどう変わったかを記録します。"
        "実際の発注や利益保証ではありません。"
    )
    if not state_path.exists():
        st.info("次回の自動分析から50万円で記録を開始します。")
        return
    with state_path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    curve = pd.DataFrame(state.get("equity_curve", []))
    latest = curve.iloc[-1] if not curve.empty else {}
    closed = state.get("closed_trades", [])
    realized = sum(_number(item.get("net_pnl")) for item in closed)
    market_value = _number(latest.get("market_value"))
    open_cost = sum(
        _number(
            item.get("entry_amount"),
            int(_number(item.get("shares"))) * _number(item.get("entry_price"))
            + _number(item.get("entry_fee")),
        )
        for item in state.get("positions", [])
    )
    unrealized = market_value - open_cost
    total_assets = _number(latest.get("total_assets"), INITIAL_CAPITAL)

    first_row = st.columns(4)
    first_row[0].metric("現在の総資産", f"{total_assets:,.0f}円", f"{total_assets - INITIAL_CAPITAL:+,.0f}円")
    first_row[1].metric("現金", f"{_number(latest.get('cash'), INITIAL_CAPITAL):,.0f}円")
    first_row[2].metric("保有株評価額", f"{market_value:,.0f}円")
    first_row[3].metric("開始から", f"{_number(latest.get('return_percent')):+.2f}%")
    second_row = st.columns(4)
    second_row[0].metric("確定損益", f"{realized:+,.0f}円")
    second_row[1].metric("含み損益", f"{unrealized:+,.0f}円")
    second_row[2].metric("最大下落", f"{_number(latest.get('drawdown_percent')):.2f}%")
    second_row[3].metric("決済件数", len(closed))

    if not curve.empty:
        _render_equity_chart(curve)

    tabs = st.tabs(["資産の流れ", "保有・注文", "売買履歴", "検証改善", "フィードバック"])
    with tabs[0]:
        ledger = build_transaction_ledger(state)
        st.markdown("#### 50万円がどう動いたか")
        if ledger.empty:
            st.caption("売買が始まると、買付・売却・現金残高を時系列で表示します。")
        else:
            st.dataframe(ledger, width="stretch", hide_index=True)
    with tabs[1]:
        _render_positions(state)
    with tabs[2]:
        history = build_trade_history(state)
        if history.empty:
            st.caption("決済後に、買値・売値・金額・損益を1行で表示します。")
        else:
            st.dataframe(history, width="stretch", hide_index=True)
    with tabs[3]:
        gains = [max(_number(item.get("net_pnl")), 0) for item in closed]
        losses = [abs(min(_number(item.get("net_pnl")), 0)) for item in closed]
        win_rate = sum(_number(item.get("net_pnl")) > 0 for item in closed) / len(closed) * 100 if closed else 0
        profit_factor = sum(gains) / sum(losses) if sum(losses) else 0
        quality = execution_quality(state)
        metrics = st.columns(4)
        metrics[0].metric("勝率", f"{win_rate:.1f}%")
        metrics[1].metric("利益係数", f"{profit_factor:.2f}")
        metrics[2].metric("約定遅延の中央値", f"{quality['median']:.0f}分")
        metrics[3].metric("10分以内の約定", f"{quality['within_10']:.1f}%")
        if quality["median"] > 10 or quality["over_60"]:
            st.warning(
                f"過去の約定には60分超の遅延が{int(quality['over_60'])}件あります。"
                "夜間シグナルが翌朝に約定していたためです。今後は市場時間内だけ注文し、"
                "同じ自動処理内で5分後価格を確認します。過去分とは分けて評価してください。"
            )
        if len(closed) < 30:
            st.info(f"決済は{len(closed)}件です。30件までは傾向、100件から比較検証として扱います。")
        causes = pd.DataFrame(state.get("cause_analysis", []))
        if not causes.empty:
            st.markdown("#### 根拠別の結果")
            st.dataframe(causes, width="stretch", hide_index=True)
        st.markdown("#### 次の改善候補")
        st.write("- TOPIXを基準にした超過リターンを追加し、地合いの上昇と実力を分離する")
        st.write("- 30件未満の根拠はスコアを自動変更せず、十分な件数まで保留する")
        st.write("- フィードバックと実績が一致した条件だけを、次の検証候補にする")
    with tabs[4]:
        _render_feedback(state)
