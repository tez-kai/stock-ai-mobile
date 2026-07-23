from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_news_records(news_json_path: str | Path) -> list[dict[str, Any]]:
    """news.json を安全に読み込んで、外れ値があっても画面停止しないようにする。"""
    path = Path(news_json_path)
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "title": str(item.get("title", "")),
                "theme": str(item.get("theme", "")),
                "source": str(item.get("source", "")),
                "published": str(item.get("published", "")),
                "url": str(item.get("url", "")),
            }
        )
    return records


def load_news_stock_links(news_stocks_json_path: str | Path) -> list[dict[str, Any]]:
    """news_stocks.json を安全に読み込んで、ticker 絞り込みの基盤を作る。"""
    path = Path(news_stocks_json_path)
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        related_companies = item.get("related_companies") or []
        if not isinstance(related_companies, list):
            related_companies = []
        records.append(
            {
                "theme": str(item.get("theme", "")),
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "related_companies": related_companies,
            }
        )
    return records


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT")
    except ValueError:
        return None


def filter_news_for_ticker(
    ticker: str,
    news_json_path: str | Path = "data/raw/news.json",
    news_stocks_json_path: str | Path = "data/raw/news_stocks.json",
) -> list[dict[str, Any]]:
    """選択中 ticker に紐づくニュースだけを抽出する。"""
    ticker = str(ticker).strip()
    if not ticker:
        return []

    news_records = load_news_records(news_json_path)
    news_stocks_links = load_news_stock_links(news_stocks_json_path)

    news_by_url: dict[str, dict[str, Any]] = {}
    for item in news_records:
        url = str(item.get("url", "")).strip()
        if url:
            news_by_url[url] = item

    matches: list[dict[str, Any]] = []
    for link in news_stocks_links:
        title = str(link.get("title", ""))
        url = str(link.get("url", ""))
        related_companies = link.get("related_companies") or []
        if not isinstance(related_companies, list):
            related_companies = []

        for company in related_companies:
            if not isinstance(company, dict):
                continue
            if str(company.get("ticker", "")) != ticker:
                continue

            news_meta = news_by_url.get(url, {})
            matches.append(
                {
                    "ticker": ticker,
                    "title": title or str(news_meta.get("title", "")),
                    "theme": str(link.get("theme", "")) or str(news_meta.get("theme", "")),
                    "source": str(news_meta.get("source", "")),
                    "published": str(news_meta.get("published", "")),
                    "url": url,
                    "match_type": str(company.get("match_type", "")),
                    "match_score": int(company.get("match_score", 0) or 0),
                }
            )

    def _sort_key(item: dict[str, Any]) -> tuple[datetime | int, str]:
        published_at = _parse_published_at(str(item.get("published", "")))
        return (published_at or datetime.min, str(item.get("title", "")))

    matches.sort(key=_sort_key, reverse=True)
    return matches
