# AI作業記録テンプレート

複数のAI（ChatGPT、Claude、Geminiなど）が対等な立場で、プロジェクトの作業記録をGitHubとGoogle Driveに残すための雛形です。新しいプロジェクトを始めるときは、このリポジトリから作ります。

## 新しいプロジェクトの作り方

1. このページの「Use this template」→「Create a new repository」で、`proj-<名前>` を Private で作る
2. 作ったリポジトリの Actions タブで「初期設定」を選び、「Run workflow」にプロジェクトの題名を入れて実行する
3. Google Drive に `AI-Projects/<リポジトリ名>/` とその中のフォルダを作る
4. `docs/project-instructions.md` の文を、各AIのプロジェクト指示に入れる

手順の詳細と、Driveのフォルダを作るときのAIへの依頼文は、手順書のリポジトリ（ai-recording-kit）の SETUP.md にあります。初期設定を実行すると、この README はプロジェクト用の内容に置き換わります。

## 入っているもの

| ファイル | 内容 |
|---|---|
| `AGENTS.md` | 記録のルール（AIが最初に読む） |
| `CLAUDE.md` `GEMINI.md` | Claude Code と Gemini CLI に AGENTS.md を読ませる1行 |
| `docs/record-format.md` | 記録の項目と書式の定義 |
| `scripts/build_index.py` | STATUS.md と索引の生成、形式の検査 |
| `scripts/init_project.py` | プロジェクトの初期設定 |
| `scripts/sync_rules.py` | テンプレートからのルールの同期 |
| `.github/workflows/` | 上の3つを動かすワークフロー |
