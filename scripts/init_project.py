#!/usr/bin/env python3
"""テンプレートから作ったリポジトリを、プロジェクト用に初期設定する。

GitHub Actions の「初期設定」（.github/workflows/init.yml）から1回だけ実行される。
README.md、docs/project-instructions.md、recording.json を作る。

使い方:
    python scripts/init_project.py --repo OWNER/NAME --title 題名 [--drive フォルダ] [--template OWNER/NAME] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "scripts" / "templates"
JST = dt.timezone(dt.timedelta(hours=9))


def render(name: str, values: dict) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="プロジェクトの初期設定")
    ap.add_argument("--repo", required=True, help="OWNER/NAME")
    ap.add_argument("--title", required=True, help="プロジェクトの題名")
    ap.add_argument("--drive", default="", help="Driveのフォルダ（空なら AI-Projects/<リポジトリ名>）")
    ap.add_argument("--template", default="", help="テンプレートのリポジトリ OWNER/NAME")
    ap.add_argument("--force", action="store_true", help="初期設定済みでも上書きする")
    args = ap.parse_args()

    config_path = ROOT / "recording.json"
    if config_path.exists() and not args.force:
        print("::error::このリポジトリは初期設定済みです（recording.json があります）。やり直す場合は force を有効にして実行してください。")
        return 1

    title = args.title.strip()
    if not title:
        print("::error::プロジェクトの題名が空です。")
        return 1
    name = args.repo.split("/")[-1]
    drive = (args.drive.strip() or f"AI-Projects/{name}").rstrip("/")
    values = {
        "REPO": args.repo,
        "REPO_NAME": name,
        "TITLE": title,
        "DRIVE": drive,
        "TEMPLATE": args.template or "（不明）",
    }

    config = {
        "format": 2,
        "repo": args.repo,
        "title": title,
        "drive_folder": drive,
        "template_repo": args.template,
        "initialized": dt.datetime.now(JST).strftime("%Y-%m-%dT%H:%M+09:00"),
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "README.md").write_text(render("README.project.md", values), encoding="utf-8")
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "project-instructions.md").write_text(render("project-instructions.md", values), encoding="utf-8")

    print(f"初期設定しました：{title}（{args.repo}、Drive：{drive}）")
    if not args.template:
        print("::warning::テンプレート元が分からなかったため、ルールの同期を使う前に recording.json の template_repo を設定してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
