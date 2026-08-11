from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
import streamlit as st


STATUS_LABELS = {
    "ACTIVE": "稼働継続",
    "WARNING": "要注意",
    "FORWARD_TEST": "実運用検証中",
    "BACKTEST": "バックテスト中",
    "CANDIDATE": "候補",
    "STOPPED": "停止済み",
    "REJECTED": "不採用",
}


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def build_monitor_rows(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """CSVの状態判定を、画面表示用の日本語列へ整形する。"""
    output: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("recommended_status", ""))
        output.append(
            {
                "戦略": str(row.get("strategy_id", "")),
                "版": int(_number(row.get("strategy_version")) or 0),
                "検証データ": "実運用" if row.get("dataset_type") == "PAPER" else "過去検証",
                "保有日数": int(_number(row.get("holding_period_days")) or 0),
                "推奨状態": STATUS_LABELS.get(status, status or "未判定"),
                "停止候補": "要確認" if _boolean(row.get("stop_candidate")) else "いいえ",
                "件数": int(_number(row.get("sample_size")) or 0),
                "期待値(%)": _number(row.get("expectancy")),
                "直近50件期待値(%)": _number(row.get("recent_50_expectancy")),
                "PF": _number(row.get("profit_factor")),
                "最大DD(%)": _number(row.get("max_drawdown")),
                "勝率(%)": _number(row.get("win_rate")),
                "判定理由": str(row.get("assessment_reasons", "")),
            }
        )
    return pd.DataFrame(output)


def select_primary_assessment(frame: pd.DataFrame, holding_days: int = 5) -> pd.Series | None:
    """日常監視では実運用を優先し、なければ過去検証を表示する。"""
    if frame.empty:
        return None
    same_horizon = frame[frame["保有日数"] == holding_days]
    if same_horizon.empty:
        same_horizon = frame
    paper = same_horizon[same_horizon["検証データ"] == "実運用"]
    return (paper if not paper.empty else same_horizon).iloc[0]


def render_strategy_monitor(rows: Iterable[dict[str, Any]]) -> None:
    st.subheader("戦略監視")
    st.caption("期待値が維持されているかを、過去検証と実運用で分けて監視します。自動停止はしません。")
    frame = build_monitor_rows(rows)
    if frame.empty:
        st.info("戦略状態は次回の定期分析後に表示されます。")
        return

    primary = select_primary_assessment(frame)
    assert primary is not None
    status = str(primary["推奨状態"])
    if str(primary["停止候補"]) == "要確認":
        st.error("現在の判定：停止候補（人の確認が必要）")
    elif status == "要注意":
        st.warning(f"現在の判定：{status}")
    else:
        st.info(f"現在の判定：{status}")

    metrics = st.columns(5)
    metrics[0].metric("評価件数", int(primary["件数"]))
    metrics[1].metric("期待値", f"{primary['期待値(%)']:.2f}%" if pd.notna(primary["期待値(%)"]) else "未評価")
    metrics[2].metric("直近50件", f"{primary['直近50件期待値(%)']:.2f}%" if pd.notna(primary["直近50件期待値(%)"]) else "蓄積中")
    metrics[3].metric("PF", f"{primary['PF']:.2f}" if pd.notna(primary["PF"]) else "未評価")
    metrics[4].metric("最大DD", f"{primary['最大DD(%)']:.2f}%" if pd.notna(primary["最大DD(%)"]) else "未評価")
    st.markdown(f"**判定理由：** {primary['判定理由'] or '評価基準を確認中'}")

    comparison = frame[frame["保有日数"] == 5][
        ["検証データ", "件数", "期待値(%)", "直近50件期待値(%)", "PF", "最大DD(%)", "勝率(%)", "推奨状態"]
    ]
    if not comparison.empty:
        st.markdown("#### 同じ5日保有で比較")
        st.dataframe(comparison, width="stretch", hide_index=True)

    with st.expander("全期間・全保有日数の判定を見る"):
        st.dataframe(frame, width="stretch", hide_index=True)
        st.caption("停止候補は提案だけです。状態変更には人の確認が必要です。")
