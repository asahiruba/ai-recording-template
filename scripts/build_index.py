#!/usr/bin/env python3
"""作業記録から STATUS.md、テーマごとの README.md、index/ を生成し、形式を検査する。

記録の形式は docs/record-format.md に定義されている。
GitHub Actions（.github/workflows/index.yml）から、記録が追加されるたびに実行される。

使い方:
    python scripts/build_index.py [--changes FILE] [--commit SHA]

    --changes  直前のプッシュで変わったファイルの一覧（git diff --name-status の出力）
    --commit   今回のコミット（変更の警告に添える）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML が必要です: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT / "themes"
INDEX_DIR = ROOT / "index"
JST = dt.timezone(dt.timedelta(hours=9))

ENTRY_RE = re.compile(r"^\d{8}T\d{4}-[a-z0-9]{4}$")
SESSION_RE = re.compile(r"^S-\d{8}-[a-z0-9]{4}$")
THEME_RE = re.compile(r"^\d{8}-[a-z0-9][a-z0-9-]{1,29}$")
SPECIAL_THEMES = {"_project", "_unsorted"}
FORMAT_VERSION = 2

FIELDS = [
    "id", "format", "title", "theme", "theme_title", "session", "type",
    "prev", "forked_from", "based_on", "supersedes", "refs",
    "author", "recorded_by", "created", "commits", "artifacts", "verbatim",
]
LIST_FIELDS = ["based_on", "supersedes", "refs", "commits", "artifacts"]
HEADINGS = {
    "work": ["依頼", "経緯", "実施内容", "判断と理由", "主張", "証拠", "未解決・残作業"],
    "review": ["対象", "確認範囲", "指摘"],
    "decision": ["対象", "判断", "判断した人", "ユーザーの発言"],
    "summary": ["現状", "未解決・残作業", "決定済みの予定"],
    "note": ["内容", "出典"],
}
TYPE_LABEL = {"work": "作業", "review": "レビュー", "decision": "判断", "summary": "まとめ", "note": "メモ"}

# AI が変更しないファイル（AGENTS.md の「変更しないもの」）
PROTECTED = {
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "recording.json",
    "docs/record-format.md", "docs/project-instructions.md",
}
PROTECTED_DIRS = ("scripts/", ".github/")
GENERATED = {"STATUS.md"}
TIMELINE_RECENT = 100
CHANGE_LOG_KEEP = 200
HEADER = "<!-- 自動生成：scripts/build_index.py。このファイルは編集しないでください。 -->\n"


# ---------------------------------------------------------------- 読み込み

@dataclass
class Entry:
    path: Path
    meta: dict
    sections: dict
    order: list
    added: str | None = None

    def get(self, key, default=None):
        return self.meta.get(key, default)

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or self.path.stem)

    @property
    def theme_dir(self) -> str:
        return self.path.parent.name

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix()

    @property
    def type(self) -> str:
        return str(self.meta.get("type") or "")

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.id)

    @property
    def sort_key(self):
        return (self.added or str(self.meta.get("created") or ""), self.id)

    def section(self, name: str) -> str:
        return self.sections.get(name, "").strip()


FRONT_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def norm_id(value) -> str | None:
    return None if value is None else str(value).strip()


def parse_entry(path: Path, problems: list) -> Entry | None:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    m = FRONT_RE.match(text)
    if not m:
        problems.append((rel, "冒頭の項目（--- で囲んだYAML）が見つかりません"))
        return None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        problems.append((rel, f"冒頭の項目をYAMLとして読めません（{str(exc).splitlines()[0]}）"))
        return None
    if not isinstance(meta, dict):
        problems.append((rel, "冒頭の項目が「項目: 値」の形になっていません"))
        return None
    for key in ("created",):
        if key in meta and meta[key] is not None:
            meta[key] = str(meta[key])
    sections, order, current = {}, [], None
    for line in m.group(2).splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            current = h.group(1)
            order.append(current)
            sections.setdefault(current, "")
        elif current is not None:
            sections[current] += line + "\n"
    return Entry(path=path, meta=meta, sections=sections, order=order)


def git_added_times() -> dict:
    """各ファイルが最初に追加されたコミットの時刻（日本時間にそろえる。git の記録が正確な順序になる）"""
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", "log", "--diff-filter=A", "--name-only",
             "--format=@%ct", "--", "themes"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    times, current = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            try:
                current = dt.datetime.fromtimestamp(int(line[1:]), JST).isoformat()
            except ValueError:
                current = None
        elif line.strip() and current:
            times[line.strip()] = current  # 古いコミットほど後に出るので、最初の追加時刻が残る
    return times


def load_entries(problems: list) -> list:
    entries = []
    times = git_added_times()
    if not THEMES_DIR.exists():
        return entries
    for theme_dir in sorted(p for p in THEMES_DIR.iterdir() if p.is_dir()):
        for path in sorted(theme_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            entry = parse_entry(path, problems)
            if entry:
                entry.added = times.get(entry.rel)
                entries.append(entry)
    entries.sort(key=lambda e: e.sort_key)
    return entries


# ---------------------------------------------------------------- 表示用

def to_jst(value: str | None) -> str:
    if not value:
        return ""
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=JST)
        return t.astimezone(JST).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def when(e: Entry) -> str:
    return to_jst(e.added) or to_jst(str(e.get("created") or ""))


def who(e: Entry) -> str:
    a = e.get("author")
    if isinstance(a, dict):
        tool = str(a.get("tool") or "不明")
        mode = str(a.get("mode") or "")
        return tool if mode in ("", "通常") else f"{tool}・{mode}"
    return str(a or "不明")


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def label(text) -> str:
    """リンクの文字として安全にする"""
    return cell(text).replace("[", "\\[").replace("]", "\\]")


def short(entry_id: str) -> str:
    return entry_id[-4:] if ENTRY_RE.match(entry_id or "") else entry_id


def link(e: Entry, base: str) -> str:
    return f"[{label(e.title)}]({base}{e.rel})"


def safe_url(url) -> str | None:
    """リンクにしてよいのは https の URL だけ"""
    url = str(url or "").strip()
    return url if re.match(r"^https://[^\s()<>]+$", url) else None


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


# ---------------------------------------------------------------- 判定

class Model:
    def __init__(self, entries: list):
        self.entries = entries
        self.by_id = {}
        for e in entries:
            self.by_id.setdefault(e.id, e)
        self.superseded_by = {}
        for e in entries:
            for old in as_list(e.get("supersedes")):
                self.superseded_by.setdefault(str(old), e.id)
        self.decisions_for = {}
        for e in entries:
            if e.type == "decision":
                for r in as_list(e.get("refs")):
                    self.decisions_for.setdefault(str(r), []).append(e)

    def active(self, e: Entry) -> bool:
        return e.id not in self.superseded_by

    def themes(self) -> dict:
        out = {}
        for e in self.entries:
            out.setdefault(e.theme_dir, []).append(e)
        return out

    def theme_title(self, theme: str, items: list) -> str:
        for e in items:
            if e.get("theme_title"):
                return str(e.get("theme_title"))
        return {"_project": "プロジェクト全体", "_unsorted": "記録先が不明な記録"}.get(theme, "")

    def review_state(self, review: Entry) -> tuple:
        decisions = sorted(self.decisions_for.get(review.id, []), key=lambda d: d.sort_key)
        if not decisions:
            return "判断待ち", None
        latest = decisions[-1]
        if "保留" in latest.section("判断"):
            return "一部保留", latest
        return "判断済み", latest

    def pending_reviews(self, items: list) -> list:
        out = []
        for e in items:
            if e.type == "review" and self.active(e):
                state, dec = self.review_state(e)
                if state != "判断済み":
                    out.append((e, state, dec))
        return out

    def forks(self, items: list) -> list:
        groups = {}
        for e in items:
            key = (str(e.get("session") or ""), norm_id(e.get("prev")))
            groups.setdefault(key, []).append(e)
        return [(k, v) for k, v in groups.items() if len(v) > 1 and k[0]]

    def latest_summary(self, items: list):
        sums = [e for e in items if e.type == "summary" and self.active(e)]
        return sums[-1] if sums else None


# ---------------------------------------------------------------- 検査

def check(model: Model, problems: list) -> list:
    out = list(problems)
    seen = {}
    for e in model.entries:
        rel = e.rel
        seen.setdefault(e.id, []).append(rel)
        missing = [f for f in FIELDS if f not in e.meta]
        if missing:
            out.append((rel, "項目が足りません：" + "、".join(missing)))
        if e.path.stem != e.id:
            out.append((rel, f"ファイル名と id（{e.id}）が一致しません"))
        if not ENTRY_RE.match(e.id):
            out.append((rel, f"id（{e.id}）の形が正しくありません"))
        theme = str(e.get("theme") or "")
        if theme != e.theme_dir:
            out.append((rel, f"theme（{theme}）が置き場所のフォルダ名と一致しません"))
        if e.theme_dir not in SPECIAL_THEMES and not THEME_RE.match(e.theme_dir):
            out.append((rel, f"テーマのフォルダ名（{e.theme_dir}）の形が正しくありません"))
        session = str(e.get("session") or "")
        if not SESSION_RE.match(session):
            out.append((rel, f"session（{session}）の形が正しくありません"))
        if e.type not in HEADINGS:
            out.append((rel, f"type（{e.type}）が5種類のどれでもありません"))
        else:
            expected = HEADINGS[e.type]
            lacking = [h for h in expected if h not in e.order]
            if lacking:
                out.append((rel, "見出しが足りません：" + "、".join(lacking)))
            else:
                positions = [e.order.index(h) for h in expected]
                if positions != sorted(positions):
                    out.append((rel, "見出しの順番が違います"))
        if e.get("format") != FORMAT_VERSION:
            out.append((rel, f"format が {e.get('format')} です（この検査は第{FORMAT_VERSION}版）"))
        for key in LIST_FIELDS:
            if key in e.meta and e.meta[key] is not None and not isinstance(e.meta[key], list):
                out.append((rel, f"{key} はリスト（[] の形）で書きます"))
        refs_fields = {"prev": [e.get("prev")], "forked_from": [e.get("forked_from")]}
        for key in ("based_on", "supersedes", "refs"):
            refs_fields[key] = as_list(e.get(key))
        for key, values in refs_fields.items():
            for v in values:
                if v is None:
                    continue
                if str(v) not in model.by_id:
                    out.append((rel, f"{key} に存在しないエントリ（{v}）があります"))
        if e.type == "review" and not as_list(e.get("refs")):
            out.append((rel, "review の refs が空です"))
        verbatim = e.get("verbatim")
        if verbatim and not (e.path.parent / str(verbatim)).exists():
            out.append((rel, f"verbatim のファイル（{verbatim}）がありません"))
        for art in as_list(e.get("artifacts")):
            if not isinstance(art, dict) or not art.get("name") or not art.get("path"):
                out.append((rel, "artifacts の各項目には name・path・url を書きます"))
            elif not safe_url(art.get("url")):
                out.append((rel, f"artifacts の url（{art.get('url')}）が https のURLではありません"))
        if e.theme_dir == "_unsorted":
            out.append((rel, "記録先が不明な記録です。正しいテーマに移す（新しいエントリで記録し直す）必要があります"))
    for theme, items in model.themes().items():
        if theme in SPECIAL_THEMES:
            continue
        if not any(i.get("theme_title") for i in items):
            out.append((f"themes/{theme}/", "theme_title が書かれたエントリがありません（テーマの最初のエントリに書きます）"))
    for entry_id, paths in seen.items():
        if len(paths) > 1:
            out.append((paths[0], f"id（{entry_id}）が重複しています：" + "、".join(paths)))
    # テーマの外に置かれたエントリらしいファイル
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", "themes/")):
            continue
        if ENTRY_RE.match(path.stem):
            out.append((rel, "エントリが themes/ の外に置かれています"))
    return out


def change_warnings(changes_file: str | None) -> list:
    if not changes_file or not Path(changes_file).exists():
        return []
    out = []
    for line in Path(changes_file).read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, paths = parts[0], parts[1:]
        for p in paths[:1]:
            kind = {"A": "追加", "M": "変更", "D": "削除", "R": "名前の変更"}.get(status[0], "変更")
            if p in PROTECTED or p.startswith(PROTECTED_DIRS):
                out.append((p, f"変更しないファイルが{kind}されました（あなたが{kind}した場合は問題ありません）"))
                continue
            if status.startswith("A"):
                continue
            if p in GENERATED or p.startswith("index/") or re.match(r"^themes/[^/]+/README\.md$", p):
                out.append((p, "自動生成のファイルが手で変更されました（次の生成で上書きされます）"))
            elif re.match(r"^themes/[^/]+/(verbatim/)?[^/]+\.md$", p):
                out.append((p, f"保存済みのエントリまたは原文が{kind}されました（訂正は新しいエントリで行います）"))
    return out


# ---------------------------------------------------------------- 生成

def render_status(model: Model, n_problems: int) -> str:
    themes = model.themes()
    lines = [HEADER, "# STATUS\n\n"]
    latest = model.entries[-1] if model.entries else None
    lines.append(f"最新の記録：{when(latest)}（{link(latest, '')}）\n" if latest else "まだ記録はありません。\n")
    if not (ROOT / "recording.json").exists():
        lines.append("\n> 初期設定がまだです。Actions の「初期設定」を実行してください。\n")
    if n_problems:
        lines.append(f"\n> 形式の警告が {n_problems} 件あります。[index/checks.md](index/checks.md) を確認してください。\n")
    if themes.get("_unsorted"):
        lines.append(f"\n> 記録先が不明な記録が {len(themes['_unsorted'])} 件あります（themes/_unsorted/）。\n")
    pending_all = []
    for items in themes.values():
        pending_all += model.pending_reviews(items)
    lines.append("\n## 判断待ち（全体）\n\n")
    if pending_all:
        for e, state, _ in pending_all:
            lines.append(f"- {link(e, '')}（{e.theme_dir}、{state}）\n")
    else:
        lines.append("なし\n")

    order = sorted(
        (t for t in themes if t != "_unsorted"),
        key=lambda t: themes[t][-1].sort_key, reverse=True,
    )
    for theme in order:
        items = themes[theme]
        title = model.theme_title(theme, items)
        lines.append(f"\n## {theme}　{title}\n\n")
        lines.append(f"最終更新：{when(items[-1])} ・ 記録 {len(items)} 件 ・ [時系列](themes/{theme}/README.md)\n")
        summary = model.latest_summary(items)
        if summary:
            lines.append(f"\nまとめ：{link(summary, '')}（{when(summary)}）\n")
            after = items[items.index(summary) + 1:]
            if after:
                names = "、".join(short(e.id) for e in after[-5:])
                lines.append(f"\n※ このまとめの後に記録が {len(after)} 件あります（{names}）。最新の状況は時系列で確認してください。\n")
            for name in HEADINGS["summary"]:
                body = summary.section(name) or "なし"
                lines.append(f"\n### {name}\n\n{body}\n")
                if name == "未解決・残作業":
                    lines.append("\n### 判断待ち\n\n")
                    pend = model.pending_reviews(items)
                    lines.append("".join(f"- {link(e, '')}（{s}）\n" for e, s, _ in pend) or "なし\n")
        else:
            active = [e for e in items if model.active(e)]
            last = active[-1] if active else items[-1]
            lines.append("\n※ まとめ（summary）がまだないため、最新の記録の残作業を表示しています。\n")
            lines.append(f"\n### 未解決・残作業\n\n{last.section('未解決・残作業') or 'なし'}（{short(last.id)}）\n")
            lines.append("\n### 判断待ち\n\n")
            pend = model.pending_reviews(items)
            lines.append("".join(f"- {link(e, '')}（{s}）\n" for e, s, _ in pend) or "なし\n")
    return "".join(lines)


def render_theme_readme(model: Model, theme: str, items: list) -> str:
    title = model.theme_title(theme, items)
    lines = [HEADER, f"# {theme}　{title}\n\n"]
    lines.append("| 日時 | 種類 | 題名 | セッション | 書いたAI | 状態 |\n|---|---|---|---|---|---|\n")
    for e in items:
        state = []
        if not model.active(e):
            state.append(f"置き換え済み（{short(model.superseded_by[e.id])}）")
        if e.type == "review":
            s, dec = model.review_state(e)
            state.append(s + (f"（{short(dec.id)}）" if dec else ""))
        lines.append(
            f"| {when(e)} | {TYPE_LABEL.get(e.type, e.type)} | [{label(e.title)}](./{e.path.name}) "
            f"| {cell(str(e.get('session') or '')[-4:])} | {cell(who(e))} | {'、'.join(state)} |\n"
        )
    forks = model.forks(items)
    lines.append("\n## 分岐\n\n")
    if forks:
        for (session, prev), group in forks:
            names = "、".join(short(g.id) for g in group)
            origin = short(prev) if prev else "セッションの最初"
            lines.append(f"- {session}：{origin} の後に {names}（後の {short(group[-1].id)} が新しい）\n")
    else:
        lines.append("なし\n")
    pend = model.pending_reviews(items)
    lines.append("\n## 判断待ちのレビュー\n\n")
    lines.append("".join(f"- [{label(e.title)}](./{e.path.name})（{s}）\n" for e, s, _ in pend) or "なし\n")
    lines.append("\n## セッションごとの流れ\n\n")
    sessions = {}
    for e in items:
        sessions.setdefault(str(e.get("session") or "不明"), []).append(e)
    for session, group in sessions.items():
        tools = []
        for g in group:
            if who(g) not in tools:
                tools.append(who(g))
        chain = " → ".join(f"{short(g.id)}（{TYPE_LABEL.get(g.type, g.type)}）" for g in group)
        lines.append(f"- {session}（{' → '.join(tools)}）：{chain}\n")
    return "".join(lines)


def render_index(model: Model, problems: list, change_log: list) -> dict:
    files = {}
    themes = model.themes()
    # themes.md
    rows = [HEADER, "# テーマ一覧\n\n| テーマ | 題名 | 記録 | 最終更新 | 最新のまとめ |\n|---|---|---|---|---|\n"]
    for theme, items in sorted(themes.items(), key=lambda kv: kv[1][-1].sort_key, reverse=True):
        s = model.latest_summary(items)
        rows.append(
            f"| [{theme}](../themes/{theme}/README.md) | {cell(model.theme_title(theme, items))} | {len(items)} "
            f"| {when(items[-1])} | {link(s, '../') if s else 'なし'} |\n"
        )
    files["themes.md"] = "".join(rows)
    # timeline
    def timeline_rows(items, base):
        out = ["| 日時 | テーマ | 種類 | 題名 | 書いたAI |\n|---|---|---|---|---|\n"]
        for e in reversed(items):
            out.append(f"| {when(e)} | {e.theme_dir} | {TYPE_LABEL.get(e.type, e.type)} | {link(e, base)} | {cell(who(e))} |\n")
        return out
    recent = model.entries[-TIMELINE_RECENT:]
    months = sorted({e.id[:6] for e in model.entries if ENTRY_RE.match(e.id)}, reverse=True)
    t = [HEADER, f"# 時系列（直近 {TIMELINE_RECENT} 件）\n\n"]
    if months:
        t.append("月別：" + " ・ ".join(f"[{m[:4]}-{m[4:]}](timeline/{m[:4]}-{m[4:]}.md)" for m in months) + "\n\n")
    t += timeline_rows(recent, "../")
    files["timeline.md"] = "".join(t)
    for m in months:
        items = [e for e in model.entries if e.id.startswith(m)]
        files[f"timeline/{m[:4]}-{m[4:]}.md"] = "".join([HEADER, f"# 時系列 {m[:4]}-{m[4:]}\n\n"] + timeline_rows(items, "../../"))
    # reviews.md
    r = [HEADER, "# レビュー一覧\n\n| 日時 | テーマ | レビュー | 書いたAI | 状態 | 判断 |\n|---|---|---|---|---|---|\n"]
    for e in reversed([x for x in model.entries if x.type == "review"]):
        state, dec = model.review_state(e)
        if not model.active(e):
            state = "置き換え済み"
        r.append(f"| {when(e)} | {e.theme_dir} | {link(e, '../')} | {cell(who(e))} | {state} | {link(dec, '../') if dec else ''} |\n")
    files["reviews.md"] = "".join(r)
    # artifacts.md
    a = [HEADER, "# 成果物の台帳（Drive）\n\n| 名前 | Driveのパス | 記録 | テーマ |\n|---|---|---|---|\n"]
    for e in reversed(model.entries):
        for art in as_list(e.get("artifacts")):
            if not isinstance(art, dict):
                continue
            name = label(art.get("name") or "")
            url = safe_url(art.get("url"))
            name_cell = f"[{name}]({url})" if url else name
            a.append(f"| {name_cell} | {cell(art.get('path') or '')} | {link(e, '../')} | {e.theme_dir} |\n")
    files["artifacts.md"] = "".join(a)
    # checks.md
    c = [HEADER, "# 形式の検査\n\n"]
    if problems:
        c.append(f"警告が {len(problems)} 件あります。\n\n| ファイル | 内容 |\n|---|---|\n")
        c += [f"| {cell(p)} | {cell(msg)} |\n" for p, msg in problems]
    else:
        c.append("警告はありません。\n")
    c.append("\n## 変更の警告（最近のもの）\n\n")
    c.append("".join(change_log[:30]) if change_log else "なし\n")
    files["checks.md"] = "".join(c)
    # entries.json
    data = []
    for e in model.entries:
        item = {k: e.meta.get(k) for k in FIELDS}
        item.update({"id": e.id, "path": e.rel, "added": e.added, "superseded_by": model.superseded_by.get(e.id)})
        data.append(item)
    files["entries.json"] = json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"
    return files


# ---------------------------------------------------------------- 実行

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--changes", help="git diff --name-status の出力ファイル")
    ap.add_argument("--commit", default="", help="今回のコミット")
    args = ap.parse_args()

    parse_problems = []
    entries = load_entries(parse_problems)
    model = Model(entries)
    problems = check(model, parse_problems)

    log_path = INDEX_DIR / "change-warnings.md"
    previous = []
    if log_path.exists():
        previous = [l for l in log_path.read_text(encoding="utf-8").splitlines(keepends=True) if l.startswith("- ")]
    stamp = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    new = [f"- {stamp} {args.commit[:7]} `{p}`：{msg}\n" for p, msg in change_warnings(args.changes)]
    change_log = (new + previous)[:CHANGE_LOG_KEEP]

    written = []
    if write_if_changed(ROOT / "STATUS.md", render_status(model, len(problems))):
        written.append("STATUS.md")
    for theme, items in model.themes().items():
        path = THEMES_DIR / theme / "README.md"
        if write_if_changed(path, render_theme_readme(model, theme, items)):
            written.append(path.relative_to(ROOT).as_posix())
    for name, content in render_index(model, problems, change_log).items():
        if write_if_changed(INDEX_DIR / name, content):
            written.append(f"index/{name}")
    if new or not log_path.exists():
        body = HEADER + "# 変更の警告の記録\n\n" + ("".join(change_log) or "なし\n")
        if write_if_changed(log_path, body):
            written.append("index/change-warnings.md")

    print(f"記録 {len(entries)} 件、警告 {len(problems)} 件、変更の警告 {len(new)} 件")
    for p, msg in problems + [(p, m) for p, m in change_warnings(args.changes)]:
        print(f"::warning file={p}::{msg}")
    print("更新したファイル：" + ("、".join(written) if written else "なし"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
