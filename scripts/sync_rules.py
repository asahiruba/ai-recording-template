#!/usr/bin/env python3
"""テンプレートから、記録のルールと仕組みのファイルを写す。

GitHub Actions の「ルールの同期」（.github/workflows/sync.yml）から実行される。
写した結果はプルリクエストにして、ユーザーが確認してから取り込む。
ワークフローのファイルは自動では書き換えられないため、違いがあれば知らせるだけにする。

安全のため、写す元と先のパスにシンボリックリンクがあれば、何も写さずに止まる。

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


class UnsafePath(Exception):
    pass


def inside(root: Path, rel: str) -> Path:
    """root の下の rel を返す。途中にシンボリックリンクがあるか、root の外を指す場合は止める。
    まだないファイルやフォルダは、そのまま作ってよい（作る場所は root の中に限られる）。"""
    if root.is_symlink():
        raise UnsafePath(f"{root} がシンボリックリンクです")
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise UnsafePath(f"{rel} は決められたフォルダの中のパスではありません")
    real_root = root.resolve(strict=True)
    p = root
    for part in rel_path.parts:
        p = p / part
        if p.is_symlink():
            raise UnsafePath(f"{p} がシンボリックリンクです")
    if not p.resolve().is_relative_to(real_root):
        raise UnsafePath(f"{p} が {root} の外を指しています")
    if p.exists() and not p.is_file():
        raise UnsafePath(f"{p} がふつうのファイルではありません")
    return p


def main() -> int:
    if len(sys.argv) != 2:
        print("使い方: python scripts/sync_rules.py <テンプレートのフォルダ>")
        return 2
    src_root = Path(sys.argv[1])

    # 先にすべてのパスを確かめ、問題があれば何も写さない
    try:
        pairs = [(rel, inside(src_root, rel), inside(ROOT, rel)) for rel in SYNC_FILES]
        flows = [(rel, inside(src_root, rel), inside(ROOT, rel)) for rel in WORKFLOWS]
    except UnsafePath as exc:
        print(f"::error::安全のため同期を止めました：{exc}")
        return 1

    changed, missing = [], []
    for rel, src, dst in pairs:
        if not src.exists():
            missing.append(rel)
            continue
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst, follow_symlinks=False)
        changed.append(rel)
    differ = [
        rel for rel, src, dst in flows
        if src.exists() and (not dst.exists() or dst.read_bytes() != src.read_bytes())
    ]
    print("更新したファイル：" + ("、".join(changed) if changed else "なし"))
    for rel in missing:
        print(f"::warning::テンプレートに {rel} がありません")
    for rel in differ:
        print(f"::notice::{rel} がテンプレートと違います。ワークフローは自動で書き換えられないため、GitHubの画面からテンプレートの内容に置き換えてください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
