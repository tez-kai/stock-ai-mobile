from __future__ import annotations

import hmac
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def require_password() -> None:
    expected = st.secrets.get("APP_PASSWORD", "")
    if not expected:
        st.error("StreamlitのSecretsに APP_PASSWORD が設定されていません。")
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.title("stock-ai")
    entered = st.text_input("パスワード", type="password")
    if st.button("ログイン", type="primary"):
        if hmac.compare_digest(entered, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("パスワードが違います。")
    st.stop()


require_password()

github_token = st.secrets.get("GITHUB_TOKEN", "")
if not github_token:
    st.error("StreamlitのSecretsに GITHUB_TOKEN が設定されていません。")
    st.stop()

from stock_ai.app.private_data import download_private_cloud_data


@st.cache_resource(ttl=300)
def prepare_cloud_data(token: str) -> str:
    destination = Path(tempfile.mkdtemp(prefix="stock-ai-data-"))
    download_private_cloud_data(token, destination)
    return str(destination)


try:
    data_root = prepare_cloud_data(github_token)
except Exception as exc:
    st.error(f"分析データを取得できませんでした: {exc}")
    st.stop()

os.environ["STOCK_AI_DATA_ROOT"] = data_root

from stock_ai.app import dashboard  # noqa: E402,F401
