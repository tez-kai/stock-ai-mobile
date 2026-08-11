from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_ai.app.chart_loader import prepare_chart_frame
from stock_ai.app.data_loader import load_dashboard_snapshot
from stock_ai.app.news_loader import filter_news_for_ticker
from stock_ai.app.intraday_paper_view import render_intraday_paper_view
from stock_ai.app.strategy_monitor_view import render_strategy_monitor
from stock_ai.app.validation_view import (
    HORIZON_LABELS,
    build_candidate_evidence,
    find_reproduced_conditions,
    summarize_conditions,
    summarize_historical_conditions,
)


TITLE = "stock-ai 投資分析ダッシュボード"
DATA_ROOT = Path(os.environ.get("STOCK_AI_DATA_ROOT", "data"))
PROCESSED_DIR = DATA_ROOT / "processed"
RAW_STOCK_DIR = DATA_ROOT / "raw" / "stocks"


def _score_to_color(score: int) -> str:
    if score >= 70:
        return "#f8d7da"
    if score >= 50:
        return "#ffe5d0"
    if score >= 30:
        return "#fff3cd"
    return "#e2e3e5"


def _style_signal_score(value: int) -> str:
    return f"background-color: {_score_to_color(value)}; color: #111;"


def _download_csv_frame(frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, encoding="utf-8")
    return buffer.getvalue().encode("utf-8")


def _build_chart_figure(windowed_frame: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=windowed_frame["Date"],
            open=windowed_frame["Open"],
            high=windowed_frame["High"],
            low=windowed_frame["Low"],
            close=windowed_frame["Close"],
            name="ローソク足",
            increasing_line_color="#2e8b57",
            decreasing_line_color="#d62728",
            legendgroup="price",
        )
    )
    fig.add_trace(go.Scatter(x=windowed_frame["Date"], y=windowed_frame["SMA5"], mode="lines", name="SMA5", line=dict(color="#ff7f0e"), legendgroup="price"))
    fig.add_trace(go.Scatter(x=windowed_frame["Date"], y=windowed_frame["SMA25"], mode="lines", name="SMA25", line=dict(color="#1f77b4"), legendgroup="price"))
    fig.add_trace(go.Scatter(x=windowed_frame["Date"], y=windowed_frame["SMA75"], mode="lines", name="SMA75", line=dict(color="#9467bd"), legendgroup="price"))

    fig.add_trace(go.Bar(x=windowed_frame["Date"], y=windowed_frame["Volume"], name="出来高", opacity=0.30, marker_color="#7f7f7f", legendgroup="volume"))

    fig.add_trace(go.Scatter(x=windowed_frame["Date"], y=windowed_frame["RSI14"], mode="lines", name="RSI14", line=dict(color="#d62728"), legendgroup="rsi"))
    fig.add_hline(y=30, line_dash="dash", line_color="#7f7f7f", annotation_text="30", annotation_position="top left")
    fig.add_hline(y=70, line_dash="dash", line_color="#7f7f7f", annotation_text="70", annotation_position="top right")

    fig.add_trace(go.Scatter(x=windowed_frame["Date"], y=windowed_frame["MACD"], mode="lines", name="MACD", line=dict(color="#17becf"), legendgroup="macd"))
    fig.add_trace(go.Scatter(x=windowed_frame["Date"], y=windowed_frame["MACD signal"], mode="lines", name="MACD signal", line=dict(color="#bcbd22"), legendgroup="macd"))

    fig.update_layout(
        title="銘柄別チャート",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        width=1100,
        height=900,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=40, r=40, b=40, t=60),
        xaxis=dict(domain=[0.0, 1.0]),
        yaxis=dict(title="価格", side="left", showgrid=True),
        yaxis2=dict(title="出来高", overlaying="y", side="right", showgrid=False),
        yaxis3=dict(title="RSI14", overlaying="y", side="right", position=0.98, showgrid=False),
        yaxis4=dict(title="MACD", overlaying="y", side="right", position=0.96, showgrid=False),
    )
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(matches=None)
    return fig


def _refresh_analysis_data() -> None:
    """クラウドに保存された最新の分析結果を再取得する。"""
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()


def _render_forward_test() -> None:
    """実運用開始後の仮想注文・保有・決済を表示する。"""
    state_path = PROCESSED_DIR / "paper_portfolio.json"
    if not state_path.exists():
        st.info("フォワードテストは、次回の分析データ更新から記録を開始します。")
        return
    with state_path.open("r", encoding="utf-8") as file:
        state = json.load(file)
    pending = state.get("pending", [])
    positions = state.get("positions", [])
    closed = state.get("closed_trades", [])
    invested = sum(float(item.get("allocation", 0) or 0) for item in positions)
    market_value = sum(
        int(item.get("shares", 0) or 0) * float(item.get("latest_close", item.get("entry_price", 0)) or 0)
        for item in positions
    )
    realized = float(state.get("cash", 0) or 0) + invested - float(state.get("initial_capital", 0) or 0)
    unrealized = market_value - invested
    cols = st.columns(6)
    cols[0].metric("注文待ち", len(pending))
    cols[1].metric("保有中", len(positions))
    cols[2].metric("決済済み", len(closed))
    cols[3].metric("現金", f"{float(state.get('cash', 0)):,.0f}円")
    cols[4].metric("実現損益", f"{realized:,.0f}円")
    cols[5].metric("含み損益", f"{unrealized:,.0f}円")
    events = state.get("events", [])
    tabs = st.tabs(["注文待ち", "保有中", "決済履歴", "更新履歴"])
    for tab, rows in zip(tabs, (pending, positions, closed, events)):
        with tab:
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            else:
                st.caption("現在、該当する記録はありません。")
    st.caption("実際の発生日以降だけを記録する仮想売買です。投資助言や将来の利益保証ではありません。")


def _render_simple_validation(snapshot) -> None:
    """根拠、結果、信頼度だけに絞った初期画面を表示する。"""
    st.subheader("期待値の検証")
    st.caption(
        "現在のスコアを売買判断としてではなく、過去の同じ根拠がその後どうなったかで検証します。"
    )

    horizon = st.selectbox(
        "検証期間",
        options=[1, 5, 20],
        format_func=lambda value: HORIZON_LABELS[value],
        index=1,
    )
    historical = summarize_historical_conditions(
        snapshot.backtest_events,
        horizon=horizon,
    )
    forward = summarize_conditions(snapshot.validation_events, horizon=horizon)
    historical_evaluated = sum(
        pd.notna(pd.to_numeric(event.get(f"return_{horizon}d"), errors="coerce"))
        for event in snapshot.backtest_events
    )
    forward_evaluated = sum(
        pd.notna(pd.to_numeric(event.get(f"return_{horizon}d"), errors="coerce"))
        for event in snapshot.validation_events
    )
    top = historical.dropna(subset=["平均リターン(%)"]).head(1)

    metrics = st.columns(4)
    metrics[0].metric("過去検証", historical_evaluated)
    metrics[1].metric("実運用の評価済み", forward_evaluated)
    metrics[2].metric("現在の候補", len(snapshot.rankings))
    metrics[3].metric(
        "過去の最高期待値",
        top.iloc[0]["根拠条件"] if not top.empty else "データ蓄積中",
        (
            f"平均 {top.iloc[0]['平均リターン(%)']:.2f}%"
            if not top.empty
            else None
        ),
    )

    tabs = st.tabs(["過去検証", "実運用検証", "両方で再現"])
    with tabs[0]:
        st.caption(
            "過去1年の株価を使い、シグナル翌営業日の始値からの値動きを検証。"
            " 往復取引コスト控除後です。"
        )
        if historical.empty:
            st.info("過去バックテスト結果がありません。分析データを更新してください。")
        else:
            st.dataframe(historical.head(15), width="stretch", hide_index=True)
    with tabs[1]:
        if forward_evaluated < 10:
            st.info(
                "実運用データは蓄積中です。10件で傾向確認、30件以上で比較検証を始めます。"
            )
        if forward.empty:
            st.caption("翌営業日以降に評価結果が順次入ります。")
        else:
            st.dataframe(forward.head(15), width="stretch", hide_index=True)
    with tabs[2]:
        reproduced = find_reproduced_conditions(historical, forward)
        if reproduced.empty:
            st.info(
                "過去検証と実運用検証の両方でプラスを確認できるまでデータを蓄積します。"
            )
        else:
            st.dataframe(reproduced.head(10), width="stretch", hide_index=True)

    st.markdown("#### 現在の候補と、過去検証による根拠")
    candidates = build_candidate_evidence(snapshot.rankings, historical)
    if candidates.empty:
        st.info("現在表示できる候補はありません。")
    else:
        st.dataframe(candidates.head(15), width="stretch", hide_index=True)

    with st.expander("数値の読み方"):
        st.markdown(
            """
- **今回の根拠**：現在のシグナルが成立した理由
- **勝率**：同じ根拠が成立した後、選択期間でプラスになった割合
- **平均リターン**：同じ根拠の選択期間後リターンの平均
- **過去検証**：保存済み株価で、同じテクニカル条件の過去成績を確認
- **実運用検証**：実装後に実際に発生したシグナルだけを追跡
- **両方で再現**：過去と実運用の双方で平均リターンがプラスだった条件
- **信頼度**：評価済み10件未満は「参考」、10件以上は「蓄積中」、30件以上は「検証可能」

勝率だけでなく、平均リターンと評価済み件数を必ず一緒に確認します。
"""
        )


def _render_dashboard() -> None:
    st.set_page_config(page_title=TITLE, layout="wide")
    st.title(TITLE)

    if st.button("分析データを更新", width="stretch"):
        _refresh_analysis_data()

    snapshot = load_dashboard_snapshot(PROCESSED_DIR)

    if snapshot.error_message:
        st.warning(snapshot.error_message)
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最終データ更新時刻", snapshot.last_updated)
    col2.metric("ニュース件数", snapshot.news_count)
    col3.metric("ニュース関連銘柄数", len(snapshot.related_tickers))
    col4.metric("分析対象銘柄数", len(snapshot.analysis_tickers))

    view_mode = st.segmented_control(
        "表示",
        options=["シンプル", "詳細分析"],
        default="シンプル",
    )
    if view_mode == "シンプル":
        render_strategy_monitor(snapshot.strategy_status_assessments)
        st.divider()
        _render_simple_validation(snapshot)
        st.divider()
        render_intraday_paper_view(PROCESSED_DIR)
        return

    with st.expander("50万円・5分後仮想売買", expanded=True):
        render_intraday_paper_view(PROCESSED_DIR)

    with st.expander("フォワードテスト（毎日の仮想売買）", expanded=True):
        _render_forward_test()

    rankings = snapshot.rankings
    if not rankings:
        st.info("表示できるランキングデータがありません。分析データ更新後に再度確認してください。")
        return

    frame = pd.DataFrame(rankings)
    frame = frame.rename(
        columns={
            "ticker": "ticker",
            "company": "正式企業名",
            "signal_score": "signal_score",
            "technical_score": "テクニカル点",
            "news_score": "ニュース点",
            "related_news_count": "関連ニュース数",
            "atr_percent": "ATR比率(%)",
            "risk_level": "値動きリスク",
            "signal_reason": "signal_reason",
        }
    )

    min_score = st.slider("最低シグナルスコア", min_value=0, max_value=100, value=0, step=1)
    search_query = st.text_input("企業名・ticker検索")
    news_only = st.checkbox("ニュースがある銘柄だけ表示", value=False)
    signal_reason_options = ["すべて"] + sorted({str(item["signal_reason"]).strip() for item in rankings if str(item["signal_reason"]).strip()})
    selected_reason = st.selectbox("シグナル理由による絞り込み", options=signal_reason_options)

    filtered = frame.copy()
    filtered = filtered[filtered["signal_score"] >= min_score]
    if news_only and "関連ニュース数" in filtered.columns:
        filtered = filtered[filtered["関連ニュース数"] > 0]

    if search_query:
        query = str(search_query).strip().lower()
        filtered = filtered[
            filtered["ticker"].str.lower().str.contains(query, na=False)
            | filtered["正式企業名"].str.lower().str.contains(query, na=False)
        ]

    if selected_reason != "すべて":
        filtered = filtered[filtered["signal_reason"].str.contains(selected_reason, na=False)]

    if filtered.empty:
        st.info("条件に一致する銘柄がありません。絞り込み条件を緩めてください。")
        return

    styled = filtered.style.map(lambda value: _style_signal_score(int(value)) if isinstance(value, (int, float)) and value >= 0 else "", subset=["signal_score"])
    st.dataframe(styled, width="stretch", hide_index=True)

    with st.expander("スコア監査（計算根拠を確認）"):
        audit_columns = [
            "ticker", "正式企業名", "テクニカル点", "関連ニュース数",
            "news_count_score", "news_freshness_score", "news_match_score",
            "ニュース点", "signal_score", "strongest_match_type",
            "latest_news_published", "ATR比率(%)", "値動きリスク", "signal_reason",
        ]
        available_columns = [column for column in audit_columns if column in filtered.columns]
        st.caption("合計点はテクニカル点＋ニュース点（上限100点）です。ニュース点は件数・鮮度・一致方法の合計です。")
        st.dataframe(filtered[available_columns], width="stretch", hide_index=True)

    st.subheader("シグナル成績記録")
    if not snapshot.signal_history:
        st.info("履歴は次回の分析データ更新から蓄積されます。")
    else:
        history_frame = pd.DataFrame(snapshot.signal_history)
        for column in ["signal_score", "return_1d", "return_5d", "return_20d"]:
            if column in history_frame.columns:
                history_frame[column] = pd.to_numeric(history_frame[column], errors="coerce")
        completed_5d = history_frame.dropna(subset=["return_5d"])
        metric_cols = st.columns(3)
        metric_cols[0].metric("記録数", len(history_frame))
        metric_cols[1].metric("5日後評価済み", len(completed_5d))
        win_rate = (completed_5d["return_5d"] > 0).mean() * 100 if not completed_5d.empty else None
        metric_cols[2].metric("5日後勝率", f"{win_rate:.1f}%" if win_rate is not None else "評価待ち")
        display_columns = [
            "signal_date", "ticker", "company", "signal_score", "entry_close",
            "return_1d", "return_5d", "return_20d", "evaluation_status",
        ]
        st.dataframe(history_frame[[c for c in display_columns if c in history_frame.columns]], width="stretch", hide_index=True)

    st.subheader("過去1年テクニカル・バックテスト")
    backtest_periods = snapshot.backtest_summary.get("periods", {})
    if not backtest_periods:
        st.info("バックテスト結果は次回の分析データ更新後に表示されます。")
    else:
        backtest_cols = st.columns(4)
        backtest_cols[0].metric("シグナル発生数", snapshot.backtest_summary.get("event_count", 0))
        entry_rule = snapshot.backtest_summary.get("entry_rule", "翌営業日始値")
        cost = float(snapshot.backtest_summary.get("transaction_cost_percent", 0.0) or 0.0)
        st.caption(f"売買前提: {entry_rule}で購入、往復コスト合計{cost:.2f}%を控除。表示成績はコスト控除後です。")
        for column, period in zip(backtest_cols[1:], ("1d", "5d", "20d")):
            result = backtest_periods.get(period, {})
            win_rate = result.get("win_rate")
            average = result.get("average_return")
            label = f"{period.replace('d', '日後')}勝率"
            column.metric(label, f"{win_rate:.1f}%" if win_rate is not None else "データ不足", delta=f"平均 {average:.2f}%" if average is not None else None)
        if snapshot.backtest_events:
            backtest_frame_data = pd.DataFrame(snapshot.backtest_events)
            display_backtest_columns = ["signal_date", "ticker", "company", "technical_score", "return_1d", "return_5d", "return_20d", "signal_reason"]
            st.dataframe(backtest_frame_data[[c for c in display_backtest_columns if c in backtest_frame_data.columns]], width="stretch", hide_index=True)

    st.subheader("バックテスト詳細分析")
    st.caption("サンプル数が少ない結果は偶然の影響を受けやすいため、件数と成績を一緒に確認してください。")
    period_label = st.selectbox("評価期間", options=["1日", "5日", "20日"], key="backtest_detail_period")
    period = {"1日": "1d", "5日": "5d", "20日": "20d"}[period_label]
    minimum_count = st.number_input("最低シグナル件数", min_value=1, value=5, step=1)
    sort_label = st.selectbox("並び順", options=["平均リターン順", "勝率順"], key="backtest_detail_sort")

    detail_tabs = st.tabs(["銘柄別", "シグナル条件別", "条件の組み合わせ別"])
    detail_sources = [
        (detail_tabs[0], snapshot.backtest_by_ticker, "ticker"),
        (detail_tabs[1], snapshot.backtest_by_reason, "signal_reason"),
        (detail_tabs[2], snapshot.backtest_by_combination, "signal_combination"),
    ]
    for tab, rows, identity_column in detail_sources:
        with tab:
            if not rows:
                st.info("詳細集計データがありません。『分析データを更新』を実行してください。")
                continue
            detail_frame = pd.DataFrame(rows)
            numeric_columns = [
                "signal_count", f"evaluated_{period}_count",
                f"average_return_{period}", f"win_rate_{period}",
            ]
            for column in numeric_columns:
                if column in detail_frame.columns:
                    detail_frame[column] = pd.to_numeric(detail_frame[column], errors="coerce")
            detail_frame = detail_frame[detail_frame["signal_count"] >= minimum_count]
            if detail_frame.empty:
                st.info("指定した最低シグナル件数を満たすデータがありません。")
                continue
            sort_column = f"average_return_{period}" if sort_label == "平均リターン順" else f"win_rate_{period}"
            detail_frame = detail_frame.sort_values(sort_column, ascending=False, na_position="last")
            columns = [identity_column]
            if identity_column == "ticker" and "company_name" in detail_frame.columns:
                columns.append("company_name")
            columns += numeric_columns
            display = detail_frame[[column for column in columns if column in detail_frame.columns]].copy()
            display = display.rename(columns={
                "signal_count": "シグナル件数",
                f"evaluated_{period}_count": "評価済み件数",
                f"average_return_{period}": "平均リターン(%)",
                f"win_rate_{period}": "勝率(%)",
            })
            st.dataframe(display, width="stretch", hide_index=True)

    st.subheader("バックテスト信頼性監査")
    robustness = snapshot.backtest_robustness
    if not robustness:
        st.info("信頼性監査データがありません。『分析データを更新』を実行してください。")
    else:
        audit_period_label = st.selectbox("監査する保有期間", options=["1日", "5日", "20日"], key="robustness_period")
        audit_period = {"1日": "1d", "5日": "5d", "20日": "20d"}[audit_period_label]
        audit = robustness.get("periods", {}).get(audit_period, {})
        audit_cols = st.columns(5)
        audit_cols[0].metric("平均", f"{audit.get('average_return', 0):.2f}%")
        audit_cols[1].metric("中央値", f"{audit.get('median_return', 0):.2f}%")
        audit_cols[2].metric("最大損失", f"{audit.get('worst_return', 0):.2f}%")
        audit_cols[3].metric("下位10%水準", f"{audit.get('percentile10_return', 0):.2f}%")
        top_share = robustness.get("top_ticker_share_percent")
        audit_cols[4].metric(
            "最大銘柄集中度",
            f"{top_share:.1f}%" if top_share is not None else "データ不足",
            delta=str(robustness.get("top_ticker", "")) or None,
        )

        reliability_tabs = st.tabs(["相場局面別", "前半・後半比較"])
        reliability_sources = [
            (reliability_tabs[0], snapshot.backtest_by_market_regime, "market_regime"),
            (reliability_tabs[1], snapshot.backtest_by_time_split, "period_group"),
        ]
        for tab, rows, identity_column in reliability_sources:
            with tab:
                if not rows:
                    st.info("表示できる監査データがありません。")
                    continue
                reliability_frame = pd.DataFrame(rows)
                selected_columns = [
                    identity_column, "signal_count", f"evaluated_{audit_period}_count",
                    f"average_return_{audit_period}", f"median_return_{audit_period}",
                    f"win_rate_{audit_period}", f"worst_return_{audit_period}",
                ]
                for column in selected_columns[1:]:
                    if column in reliability_frame.columns:
                        reliability_frame[column] = pd.to_numeric(reliability_frame[column], errors="coerce")
                reliability_frame = reliability_frame[[c for c in selected_columns if c in reliability_frame.columns]]
                reliability_frame = reliability_frame.rename(columns={
                    "signal_count": "シグナル件数",
                    f"evaluated_{audit_period}_count": "評価済み件数",
                    f"average_return_{audit_period}": "平均リターン(%)",
                    f"median_return_{audit_period}": "中央値(%)",
                    f"win_rate_{audit_period}": "勝率(%)",
                    f"worst_return_{audit_period}": "最大損失(%)",
                })
                st.dataframe(reliability_frame, width="stretch", hide_index=True)
        st.caption("後半（検証期間）の成績が前半より大きく悪化する場合、過去データへの合わせすぎに注意が必要です。")

    st.subheader("損切り・利確ルール比較（20日保有）")
    if not snapshot.backtest_exit_strategies:
        st.info("損切り・利確の比較データがありません。『分析データを更新』を実行してください。")
    else:
        strategy_frame = pd.DataFrame(snapshot.backtest_exit_strategies)
        strategy_numeric_columns = [
            "trade_count", "average_return", "median_return", "win_rate", "worst_return",
            "best_return", "sum_return", "average_holding_days", "stop_exit_count", "take_profit_exit_count",
        ]
        for column in strategy_numeric_columns:
            strategy_frame[column] = pd.to_numeric(strategy_frame[column], errors="coerce")
        strategy_sort = st.selectbox(
            "ルールの並び順",
            options=["平均リターン順", "最大損失が小さい順", "勝率順"],
            key="exit_strategy_sort",
        )
        if strategy_sort == "平均リターン順":
            strategy_frame = strategy_frame.sort_values("average_return", ascending=False)
        elif strategy_sort == "最大損失が小さい順":
            strategy_frame = strategy_frame.sort_values("worst_return", ascending=False)
        else:
            strategy_frame = strategy_frame.sort_values("win_rate", ascending=False)
        strategy_display = strategy_frame.rename(columns={
            "strategy": "売買ルール", "trade_count": "取引数", "average_return": "平均リターン(%)",
            "median_return": "中央値(%)", "win_rate": "勝率(%)", "worst_return": "最大損失(%)",
            "best_return": "最大利益(%)", "sum_return": "単純合計リターン(%)",
            "average_holding_days": "平均保有日数", "stop_exit_count": "損切り件数",
            "take_profit_exit_count": "利確件数",
        })
        st.dataframe(strategy_display, width="stretch", hide_index=True)
        st.caption("同日に損切りと利確へ到達した場合は損切り優先。往復コスト0.20%控除後の比較です。")

    st.subheader("損切り・利確ルールの安定性")
    if not snapshot.backtest_exit_strategy_stability:
        st.info("安定性データがありません。『分析データを更新』を実行してください。")
    else:
        stability_frame = pd.DataFrame(snapshot.backtest_exit_strategy_stability)
        stability_numeric = [
            "first_trade_count", "second_trade_count", "first_average_return", "second_average_return",
            "first_win_rate", "second_win_rate", "first_worst_return", "second_worst_return",
            "average_return_gap", "win_rate_gap", "stability_score",
        ]
        for column in stability_numeric:
            stability_frame[column] = pd.to_numeric(stability_frame[column], errors="coerce")
        stability_sort = st.selectbox(
            "安定性の並び順", options=["安定性スコア順", "平均リターン順"], key="exit_stability_sort"
        )
        if stability_sort == "安定性スコア順":
            stability_frame = stability_frame.sort_values("stability_score", ascending=False)
        else:
            stability_frame["combined_average_return"] = (
                stability_frame["first_average_return"] + stability_frame["second_average_return"]
            ) / 2
            stability_frame = stability_frame.sort_values("combined_average_return", ascending=False)
        stability_display = stability_frame[[
            "strategy", "first_trade_count", "second_trade_count", "first_average_return",
            "second_average_return", "first_win_rate", "second_win_rate", "average_return_gap",
            "first_worst_return", "second_worst_return", "stability_score", "stability_rating",
        ]].rename(columns={
            "strategy": "売買ルール", "first_trade_count": "前半取引数", "second_trade_count": "後半取引数",
            "first_average_return": "前半平均リターン(%)", "second_average_return": "後半平均リターン(%)",
            "first_win_rate": "前半勝率(%)", "second_win_rate": "後半勝率(%)",
            "average_return_gap": "平均リターン差", "first_worst_return": "前半最大損失(%)",
            "second_worst_return": "後半最大損失(%)", "stability_score": "安定性スコア",
            "stability_rating": "安定性判定",
        })
        st.dataframe(stability_display, width="stretch", hide_index=True)
        st.caption("同じシグナル日は同じ期間にまとめ、前後半の再現性・件数・損失を0～100点で評価しています。")

    st.subheader("ポートフォリオ・バックテスト")
    portfolio_summary = snapshot.portfolio_backtest_summary
    if not portfolio_summary or not snapshot.portfolio_backtest:
        st.info("ポートフォリオ検証データがありません。『分析データを更新』を実行してください。")
    else:
        portfolio_cols = st.columns(6)
        portfolio_cols[0].metric("初期資金", f"{float(portfolio_summary.get('initial_capital', 0)):,.0f}円")
        portfolio_cols[1].metric("最終資産", f"{float(portfolio_summary.get('final_capital', 0)):,.0f}円")
        portfolio_cols[2].metric("総合損益率", f"{float(portfolio_summary.get('total_return', 0)):.2f}%")
        portfolio_cols[3].metric("最大ドローダウン", f"{float(portfolio_summary.get('max_drawdown', 0)):.2f}%")
        portfolio_cols[4].metric("実行取引", int(portfolio_summary.get("executed_trades", 0)))
        portfolio_cols[5].metric("見送り", int(portfolio_summary.get("skipped_trades", 0)))
        st.caption(
            f"採用ルール: {portfolio_summary.get('strategy', '')}／最大保有数: "
            f"{portfolio_summary.get('max_positions', 0)}／{portfolio_summary.get('equity_basis', '')}"
        )
        portfolio_frame = pd.DataFrame(snapshot.portfolio_backtest)
        for column in ("equity", "drawdown", "net_return", "allocation"):
            portfolio_frame[column] = pd.to_numeric(portfolio_frame[column], errors="coerce")
        portfolio_frame["exit_date"] = pd.to_datetime(portfolio_frame["exit_date"], errors="coerce")
        equity_frame = portfolio_frame.dropna(subset=["exit_date", "equity"]).set_index("exit_date")[["equity"]]
        if not equity_frame.empty:
            st.line_chart(equity_frame, y="equity", y_label="資産額（円）", x_label="決済日")
        with st.expander("取引明細を表示"):
            portfolio_display = portfolio_frame[[
                "ticker", "company", "entry_date", "exit_date", "allocation", "net_return",
                "exit_reason", "proceeds", "equity", "drawdown",
            ]].rename(columns={
                "ticker": "ticker", "company": "企業名", "entry_date": "購入日", "exit_date": "決済日",
                "allocation": "投資額", "net_return": "リターン(%)", "exit_reason": "決済理由",
                "proceeds": "回収額", "equity": "実現資産額", "drawdown": "ドローダウン(%)",
            })
            st.dataframe(portfolio_display, width="stretch", hide_index=True)
        st.caption("資産曲線とドローダウンは決済済み取引の実現損益を基準にしています。保有中の含み損益は含みません。")

    csv_bytes = _download_csv_frame(filtered)
    st.download_button(
        label="CSVダウンロード",
        data=csv_bytes,
        file_name="stock_ai_ranking.csv",
        mime="text/csv",
        width="stretch",
    )

    st.subheader("銘柄別チャート")
    selected_ticker = st.selectbox("銘柄を選択", options=[row["ticker"] for row in rankings])
    selected_row = next((row for row in rankings if row["ticker"] == selected_ticker), None)
    if selected_row is None:
        st.info("選択できる銘柄がありません。ランキングデータを確認してください。")
        return

    stock_csv_path = RAW_STOCK_DIR / f"{selected_ticker}.csv"
    selected_period = st.selectbox("表示期間", options=["1か月", "3か月", "6か月", "1年"])
    windowed_frame = prepare_chart_frame(stock_csv_path, selected_period)
    if windowed_frame.empty:
        st.info("選択した銘柄の株価データが見つかりません。まず `python -m stock_ai.main` を実行して、`data/raw/stocks` に CSV を作成してください。")
        return

    latest_row = windowed_frame.iloc[-1]
    latest_signal = selected_row.get("signal_reason", "")
    if isinstance(latest_signal, list):
        latest_signal = "; ".join(str(item) for item in latest_signal)
    latest_score = int(selected_row.get("signal_score", 0) or 0)
    latest_close = float(latest_row["Close"])
    latest_volume = int(latest_row["Volume"])
    rsi_value = latest_row.get("RSI14")
    macd_value = latest_row.get("MACD")

    summary_cols = st.columns(6)
    summary_cols[0].metric("ticker", selected_ticker)
    summary_cols[1].metric("正式企業名", selected_row.get("company", selected_ticker))
    summary_cols[2].metric("signal_score", latest_score)
    summary_cols[3].metric("signal_reason", latest_signal)
    summary_cols[4].metric("テクニカル点", int(selected_row.get("technical_score", 0) or 0))
    summary_cols[5].metric("ニュース点", int(selected_row.get("news_score", 0) or 0))

    with st.expander("この銘柄のスコア計算内訳"):
        audit_cols = st.columns(4)
        audit_cols[0].metric("ニュース件数点", int(selected_row.get("news_count_score", 0) or 0))
        audit_cols[1].metric("ニュース鮮度点", int(selected_row.get("news_freshness_score", 0) or 0))
        audit_cols[2].metric("一致方法点", int(selected_row.get("news_match_score", 0) or 0))
        audit_cols[3].metric("最も強い一致", selected_row.get("strongest_match_type", "-") or "-")
        st.caption(f"最新関連ニュース: {selected_row.get('latest_news_published', '') or 'なし'}")

    st.markdown("### 主要指標")
    info_cols = st.columns(5)
    info_cols[0].metric("最新終値", f"{latest_close:,.0f}")
    info_cols[1].metric("最新出来高", f"{latest_volume:,}")
    info_cols[2].metric("RSI14", f"{rsi_value:.2f}" if pd.notna(rsi_value) else "データ不足")
    info_cols[3].metric("MACD", f"{macd_value:.2f}" if pd.notna(macd_value) else "データ不足")
    info_cols[4].metric("値動きリスク", selected_row.get("risk_level", "-") or "-")

    st.plotly_chart(_build_chart_figure(windowed_frame), width="stretch")

    st.subheader("関連ニュース一覧")
    news_limit = st.selectbox("表示件数", options=[5, 10, 20, "すべて"])
    news_items = []
    try:
        news_items = filter_news_for_ticker(
            selected_ticker,
            DATA_ROOT / "raw" / "news.json",
            DATA_ROOT / "raw" / "news_stocks.json",
        )
    except Exception:
        news_items = []

    if not news_items:
        st.info("この銘柄に関連するニュースはありません")
    else:
        if news_limit == "すべて":
            displayed_news = news_items
        else:
            displayed_news = news_items[: int(news_limit)]

        for item in displayed_news:
            title = str(item.get("title", "")).strip() or "タイトルなし"
            url = str(item.get("url", "")).strip()
            theme = str(item.get("theme", "")).strip() or "-"
            source = str(item.get("source", "")).strip() or "-"
            published = str(item.get("published", "")).strip() or "-"
            match_type = str(item.get("match_type", "")).strip() or "-"
            match_score = item.get("match_score", "-")

            if url:
                st.markdown(f"- [{title}]({url})")
            else:
                st.markdown(f"- {title}")
            st.caption(
                f"テーマ: {theme} | 情報源: {source} | 公開日時: {published} | 一致方法: {match_type} | 一致スコア: {match_score}"
            )


if __name__ == "__main__":
    _render_dashboard()
