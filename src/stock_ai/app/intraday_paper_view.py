from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


def render_intraday_paper_view(processed_dir: Path) -> None:
    state_path = processed_dir / "intraday_paper_portfolio.json"
    st.subheader("50万円・5分後仮想売買")
    st.caption(
        "シグナル発信5分後以降の最初の5分足で約定したと仮定します。"
        "無料データによる検証であり、実際の発注や利益保証ではありません。"
    )
    if not state_path.exists():
        st.info("次回の自動分析から50万円で記録を開始します。")
        return
    with state_path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    curve = pd.DataFrame(state.get("equity_curve", []))
    latest = curve.iloc[-1] if not curve.empty else {}
    positions = state.get("positions", [])
    closed = state.get("closed_trades", [])
    metrics = st.columns(6)
    metrics[0].metric("総資産", f"{float(latest.get('total_assets', 500000)):,.0f}円")
    metrics[1].metric("損益", f"{float(latest.get('pnl', 0)):,.0f}円")
    metrics[2].metric("収益率", f"{float(latest.get('return_percent', 0)):.2f}%")
    metrics[3].metric("最大下落", f"{float(latest.get('drawdown_percent', 0)):.2f}%")
    metrics[4].metric("保有中", len(positions))
    metrics[5].metric("決済済み", len(closed))

    if not curve.empty:
        chart = curve.copy()
        chart["timestamp"] = pd.to_datetime(chart["timestamp"], errors="coerce")
        st.line_chart(chart.set_index("timestamp")[["total_assets"]], height=320)

    tabs = st.tabs(["いまの状態", "売買結果", "原因分析", "ルール"])
    with tabs[0]:
        pending = state.get("pending_orders", [])
        if pending:
            st.caption("5分後の価格待ち")
            st.dataframe(pd.DataFrame(pending), width="stretch", hide_index=True)
        if positions:
            st.caption("保有中")
            st.dataframe(pd.DataFrame(positions), width="stretch", hide_index=True)
        if not pending and not positions:
            st.caption("現在、待機中の注文・保有銘柄はありません。")
    with tabs[1]:
        if closed:
            st.dataframe(pd.DataFrame(closed), width="stretch", hide_index=True)
        else:
            st.caption("決済後に、利益・損失・約定遅延を表示します。")
    with tabs[2]:
        causes = pd.DataFrame(state.get("cause_analysis", []))
        if causes.empty:
            st.caption("決済データを蓄積すると、根拠別の勝率と平均リターンを表示します。")
        else:
            st.dataframe(causes, width="stretch", hide_index=True)
            best = causes.iloc[0]
            st.info(
                f"現在の最高期待値層：{best['根拠']}／"
                f"{int(best['取引数'])}件／平均{float(best['平均リターン(%)']):.2f}%"
            )
    with tabs[3]:
        for value in state.get("rules", {}).values():
            st.write(f"- {value}")
