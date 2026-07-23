from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import requests


ARCHIVE_URL = "https://api.github.com/repos/tez-kai/stock-ai/zipball/main"


def download_private_cloud_data(token: str, destination: Path) -> Path:
    """Download only cloud_data from the private stock-ai repository."""
    response = requests.get(
        ARCHIVE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=60,
    )
    response.raise_for_status()

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        members = [
            name
            for name in archive.namelist()
            if "/cloud_data/" in name and not name.endswith("/")
        ]
        if not members:
            raise RuntimeError("非公開リポジトリに cloud_data が見つかりません。")

        for member in members:
            relative = member.split("/cloud_data/", 1)[1]
            output_path = destination / relative
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, output_path.open("wb") as target:
                shutil.copyfileobj(source, target)

    return destination
