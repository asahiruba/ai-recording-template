# {{TITLE}}

このリポジトリは、プロジェクト「{{TITLE}}」の作業記録です。複数のAI（ChatGPT、Claude、Geminiなど）とユーザーが、同じ形式で記録を残しています。

- 成果物（Word、PDF、スライド、表、画像、データ）：Google Drive の `{{DRIVE}}/`
- 記録のルール：[AGENTS.md](AGENTS.md)
- 記録の形式：[docs/record-format.md](docs/record-format.md)

## 読み方

1. [STATUS.md](STATUS.md)：全体の現状と判断待ち（自動生成）
2. `themes/<テーマID>/README.md`：テーマごとの時系列と分岐（自動生成）
3. `themes/<テーマID>/<エントリID>.md`：作業の区切りごとの記録

検索用の索引は [index/](index/) にあります。原文（`verbatim/`）は、正確さを確かめるときに読みます。

## AIとの会話の始め方

新しい会話の最初に、次の1行を書きます。

```text
【記録先】{{REPO_NAME}} ／ テーマ：<テーマID> ／ セッション：新規
```

- 新しいテーマを始めるときは、テーマを `新規 <英数字の名前>「<題名>」` にします。
- 記録しない会話は、最初に【記録不要】と書きます。
- 各AIのプロジェクト指示に入れる文は [docs/project-instructions.md](docs/project-instructions.md) にあります。

## 構成

```text
AGENTS.md  CLAUDE.md  GEMINI.md   記録のルール
README.md                         このファイル
STATUS.md                         現状（自動生成）
recording.json                    プロジェクトの設定
docs/                             記録の形式、プロジェクト指示の文
index/                            索引と形式の検査（自動生成）
themes/<テーマID>/                記録（要約と verbatim/ の原文）
scripts/  .github/workflows/      自動生成と初期設定の仕組み
```

## ルールの更新

テンプレート（{{TEMPLATE}}）のルールが更新されたら、Actions の「ルールの同期」を実行します。
