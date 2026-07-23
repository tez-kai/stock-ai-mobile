# stock-ai mobile dashboard

スマートフォンから `stock-ai` の分析結果を確認するための表示専用アプリです。

- 分析本体と生成データは非公開リポジトリ `tez-kai/stock-ai` に保持します。
- この公開リポジトリにはAPIキーや分析データを保存しません。
- Streamlit Community CloudのSecretsに、画面パスワードと読み取り専用GitHubトークンを設定します。

## Streamlit Secrets

```toml
APP_PASSWORD = "自分で決めた長いパスワード"
GITHUB_TOKEN = "stock-aiだけを読み取れるfine-grained token"
```

トークンやパスワードをGitHubへコミットしないでください。
