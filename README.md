# stock-ai mobile dashboard

スマートフォンから `stock-ai` の分析結果を確認するための表示専用アプリです。

- 分析本体と生成データは非公開リポジトリ `tez-kai/stock-ai` に保持します。
- この公開リポジトリにはAPIキーや分析データを保存しません。
- Streamlit Community CloudのSecretsに、画面パスワードと読み取り専用GitHubトークンを設定します。

## 戦略監視

- 全期間と直近50件の期待値を比較します。
- 過去検証と実運用検証を分離して表示します。
- 稼働継続・要注意・停止候補と、その判定理由を表示します。
- 自動停止は行わず、最終判断には人の確認を必要とします。

## Streamlit Secrets

```toml
APP_PASSWORD = "自分で決めた長いパスワード"
GITHUB_TOKEN = "stock-aiだけを読み取れるfine-grained token"
```

トークンやパスワードをGitHubへコミットしないでください。
