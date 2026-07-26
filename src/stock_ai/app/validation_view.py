from __future__ import annotations

import json
from typing import Any

import pandas as pd


HORIZON_LABELS = {
    1: "翌営業日",
    3: "3営業日後",
    5: "5営業日後",
    10: "10営業日後",
    20: "20営業日後",
}


def _conditions(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return [item.strip() for item in text.split(";") if item.strip()]
    if isinstance(decoded, list):
        return [str(item).strip() for item in decoded if str(item).strip()]
    return [str(decoded).strip()] if str(decoded).strip() else []


def confidence_label(evaluated_count: int) -> str:
    if evaluated_count >= 30:
        return "検証可能"
    if evaluated_count >= 10:
        return "蓄積中"
    return "参考"


def summarize_conditions(
    events: list[dict[str, Any]],
    horizon: int = 5,
) -> pd.DataFrame:
    """根拠条件ごとの件数・勝率・平均リターンを集計する。"""
    return_column = f"return_{horizon}d"
    rows: list[dict[str, Any]] = []
    for event in events:
        conditions = (
            _conditions(event.get("technical_conditions"))
            + _conditions(event.get("news_conditions"))
            + _conditions(event.get("fundamental_conditions"))
            + _conditions(event.get("market_conditions"))
        )
        for condition in dict.fromkeys(conditions):
            rows.append(
                {
                    "condition": condition,
                    "return": pd.to_numeric(event.get(return_column), errors="coerce"),
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "根拠条件",
                "発生件数",
                "評価済み",
                "勝率(%)",
                "平均リターン(%)",
                "中央値(%)",
                "信頼度",
            ]
        )

    source = pd.DataFrame(rows)
    summaries: list[dict[str, Any]] = []
    for condition, group in source.groupby("condition", sort=False):
        evaluated = group["return"].dropna()
        summaries.append(
            {
                "根拠条件": condition,
                "発生件数": len(group),
                "評価済み": len(evaluated),
                "勝率(%)": round(float((evaluated > 0).mean() * 100), 1)
                if not evaluated.empty
                else None,
                "平均リターン(%)": round(float(evaluated.mean()), 2)
                if not evaluated.empty
                else None,
                "中央値(%)": round(float(evaluated.median()), 2)
                if not evaluated.empty
                else None,
                "信頼度": confidence_label(len(evaluated)),
            }
        )

    result = pd.DataFrame(summaries)
    result["_average"] = pd.to_numeric(result["平均リターン(%)"], errors="coerce")
    result = result.sort_values(
        ["_average", "評価済み"],
        ascending=[False, False],
        na_position="last",
    )
    return result.drop(columns=["_average"]).reset_index(drop=True)


def summarize_historical_conditions(
    events: list[dict[str, Any]],
    horizon: int = 5,
) -> pd.DataFrame:
    """過去バックテストをシグナル根拠ごとに集計する。"""
    return_column = f"return_{horizon}d"
    rows: list[dict[str, Any]] = []
    for event in events:
        conditions = _conditions(event.get("signal_reason"))
        market_regime = str(event.get("market_regime", "")).strip()
        if market_regime:
            conditions.append(f"市場環境：{market_regime}")
        value = pd.to_numeric(event.get(return_column), errors="coerce")
        for condition in dict.fromkeys(conditions):
            rows.append({"condition": condition, "return": value})
    return _summarize_rows(rows)


def _summarize_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "根拠条件",
        "発生件数",
        "評価済み",
        "勝率(%)",
        "平均リターン(%)",
        "中央値(%)",
        "信頼度",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    source = pd.DataFrame(rows)
    summaries: list[dict[str, Any]] = []
    for condition, group in source.groupby("condition", sort=False):
        evaluated = group["return"].dropna()
        summaries.append(
            {
                "根拠条件": condition,
                "発生件数": len(group),
                "評価済み": len(evaluated),
                "勝率(%)": round(float((evaluated > 0).mean() * 100), 1)
                if not evaluated.empty
                else None,
                "平均リターン(%)": round(float(evaluated.mean()), 2)
                if not evaluated.empty
                else None,
                "中央値(%)": round(float(evaluated.median()), 2)
                if not evaluated.empty
                else None,
                "信頼度": confidence_label(len(evaluated)),
            }
        )
    result = pd.DataFrame(summaries)
    result["_average"] = pd.to_numeric(result["平均リターン(%)"], errors="coerce")
    return (
        result.sort_values(
            ["_average", "評価済み"],
            ascending=[False, False],
            na_position="last",
        )
        .drop(columns=["_average"])
        .reset_index(drop=True)
    )


def find_reproduced_conditions(
    historical: pd.DataFrame,
    forward: pd.DataFrame,
) -> pd.DataFrame:
    """過去検証と実運用検証の双方でプラスだった条件を返す。"""
    if historical.empty or forward.empty:
        return pd.DataFrame()
    merged = historical.merge(
        forward,
        on="根拠条件",
        suffixes=("_過去", "_実運用"),
    )
    for column in ("平均リターン(%)_過去", "平均リターン(%)_実運用"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    reproduced = merged[
        (merged["平均リターン(%)_過去"] > 0)
        & (merged["平均リターン(%)_実運用"] > 0)
    ].copy()
    if reproduced.empty:
        return reproduced
    reproduced["再現スコア"] = (
        reproduced["平均リターン(%)_過去"]
        + reproduced["平均リターン(%)_実運用"]
    ).round(2)
    columns = [
        "根拠条件",
        "評価済み_過去",
        "勝率(%)_過去",
        "平均リターン(%)_過去",
        "評価済み_実運用",
        "勝率(%)_実運用",
        "平均リターン(%)_実運用",
        "再現スコア",
    ]
    return reproduced[columns].sort_values("再現スコア", ascending=False)


def build_candidate_evidence(
    rankings: list[dict[str, Any]],
    condition_summary: pd.DataFrame,
) -> pd.DataFrame:
    """現在の候補に、その根拠と最も強い過去検証結果を付ける。"""
    if not rankings:
        return pd.DataFrame()

    summary_by_condition = (
        condition_summary.set_index("根拠条件").to_dict("index")
        if not condition_summary.empty
        else {}
    )
    rows: list[dict[str, Any]] = []
    for ranking in rankings:
        reasons = _conditions(ranking.get("signal_reason"))
        matched = [
            (reason, summary_by_condition[reason])
            for reason in reasons
            if reason in summary_by_condition
            and summary_by_condition[reason].get("平均リターン(%)") is not None
        ]
        matched.sort(
            key=lambda item: (
                float(item[1].get("平均リターン(%)") or -999),
                int(item[1].get("評価済み") or 0),
            ),
            reverse=True,
        )
        best_reason, best = matched[0] if matched else ("評価待ち", {})
        rows.append(
            {
                "ticker": ranking.get("ticker", ""),
                "企業名": ranking.get("company", ""),
                "現在スコア": int(ranking.get("signal_score", 0) or 0),
                "今回の根拠": " / ".join(reasons) if reasons else "根拠なし",
                "過去に最も強い根拠": best_reason,
                "評価済み": int(best.get("評価済み", 0) or 0),
                "勝率(%)": best.get("勝率(%)"),
                "平均リターン(%)": best.get("平均リターン(%)"),
                "信頼度": best.get("信頼度", "評価待ち"),
            }
        )
    return pd.DataFrame(rows).sort_values("現在スコア", ascending=False)
