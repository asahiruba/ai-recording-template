#!/usr/bin/env python3
"""テンプレートから、記録のルールと仕組みのファイルを写す。

GitHub Actions の「ルールの同期」（.github/workflows/sync.yml）から実行される。
ワークフローのファイルは自動では書き換えられないため、違いがあれば知らせるだけにする。

使い方:
    python scripts/sync_rules.py <テンプレートを取得したフォルダ>
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SYNC_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "docs/record-format.md",
    "scripts/build_index.py",
    "scripts/init_project.py",
    "scripts/sync_rules.py",
    "scripts/templates/README.project.md",
    "scripts/templates/project-instructions.md",
]
WORKFLOWS = [
    ".github/workflows/index.yml",
    ".github/workflows/init.yml",
    ".github/workflows/sync.yml",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("使い方: python scripts/sync_rules.py <テンプレートのフォルダ>")
        return 2
    src_root = Path(sys.argv[1])
    changed, missing = [], []
    for rel in SYNC_FILES:
        src, dst = src_root / rel, ROOT / rel
        if not src.exists():
            missing.append(rel)
            continue
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        changed.append(rel)
    differ = [
        rel for rel in WORKFLOWS
        if (src_root / rel).exists() and (
            not (ROOT / rel).exists() or (ROOT / rel).read_bytes() != (src_root / rel).read_bytes()
        )
    ]
    print("更新したファイル：" + ("、".join(changed) if changed else "なし"))
    for rel in missing:
        print(f"::warning::テンプレートに {rel} がありません")
    for rel in differ:
        print(f"::notice::{rel} がテンプレートと違います。ワークフローは自動で書き換えられないため、GitHubの画面からテンプレートの内容に置き換えてください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
