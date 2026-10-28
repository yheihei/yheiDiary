#!/usr/bin/env python3
"""Turn one local diary manuscript into the private JSON the other scripts use.

The manuscript is never modified. Its file name must look like
"YYYYMMDD - タイトル.md": the date becomes the slug prefix and the
publication date (21:00 JST that day), and the rest becomes the title.

Writes private/drafts/<slug>.post.json ({title, content}) and
private/drafts/<slug>.source.json (where it came from and what it contains).
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import shutil
import sys

from common import PRIVATE_DRAFTS, ROOT, Stop, check_slug, load_sidecar, save_sidecar, sidecar_path, write_private

FILENAME = re.compile(r"(?P<date>\d{8}) - (?P<title>.+)\.md\Z")
FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.S)
X_URL = re.compile(r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/\w+/status(?:es)?/\d+(?:[/?#]\S*)?")
URL_ONLY = re.compile(r"<?(https?://\S+?)>?")
MD_IMAGE = re.compile(r"!\[[^\]]*\]\((\S+?)(?:\s+\"[^\"]*\")?\)")
WIKI_EMBED = re.compile(r"!\[\[([^\]]+)\]\]")


def parse_manuscript(path: Path) -> dict:
    match = FILENAME.fullmatch(path.name)
    if not match:
        raise Stop("原稿のファイル名は「YYYYMMDD - タイトル.md」の形にしてください。")
    raw = match["date"]
    try:
        day = date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError as exc:
        raise Stop("ファイル名の日付が正しくありません。") from exc
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta = {}
    front = FRONTMATTER.match(text)
    if front:
        for line in front["body"].splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip()
        text = text[front.end():]
    body = text.strip("\n")
    if not body.strip():
        raise Stop("原稿の本文が空です。")

    x_posts, other_links = [], []
    for line in body.splitlines():
        only = URL_ONLY.fullmatch(line.strip())
        if not only:
            continue
        url = only[1]
        (x_posts if X_URL.fullmatch(url) else other_links).append(url)
    unresolved = WIKI_EMBED.findall(body)
    images = MD_IMAGE.findall(body)
    local_images = [src for src in images if not src.startswith("https://")]
    return {
        "date": day,
        "title": match["title"].strip(),
        "body": body,
        "meta": meta,
        "images": images,
        "xPosts": x_posts,
        "otherLinks": other_links,
        "unresolved": unresolved + local_images,
    }


def prepare(manuscript: str, name: str, title: str | None = None) -> dict:
    path = Path(manuscript).expanduser().resolve()
    if not path.is_file():
        raise Stop("原稿が見つかりません: " + manuscript)
    parsed = parse_manuscript(path)
    if parsed["unresolved"]:
        raise Stop("公開URLのない画像があります。本人に確かめてください: " + ", ".join(parsed["unresolved"]))
    slug = parsed["date"].strftime("%Y%m%d") + "-" + name
    check_slug(slug)
    title = (title or parsed["title"]).strip()

    previous = load_sidecar(slug) if sidecar_path(slug).is_file() else {}
    if previous.get("id"):
        raise Stop("この slug の記事は作成済みです（記事 ID " + previous["id"] + "）。直すなら SKILL.md の「公開済みの記事を直す」へ。")

    post = {"title": title, "content": parsed["body"] + "\n"}
    write_private(PRIVATE_DRAFTS / (slug + ".post.json"), json.dumps(post, ensure_ascii=False, indent=2) + "\n")
    copy = PRIVATE_DRAFTS / (slug + ".source.md")
    shutil.copyfile(path, copy)
    copy.chmod(0o600)

    source = {
        **previous,
        "source": str(path),
        "sourceCopy": str(copy.relative_to(ROOT)),
        "sourceMetadata": parsed["meta"],
        "slug": slug,
        "title": title,
        "sourceDate": parsed["date"].isoformat(),
        "publishedAt": parsed["date"].isoformat() + "T21:00:00+09:00",
        "images": parsed["images"],
        "xPosts": parsed["xPosts"],
        "otherLinks": parsed["otherLinks"],
    }
    save_sidecar(slug, source)
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare one diary manuscript for yhei.dev")
    parser.add_argument("manuscript", help="Path to 'YYYYMMDD - タイトル.md'")
    parser.add_argument("--name", required=True,
                        help="English slug part after the date, e.g. vulnerability-fest")
    parser.add_argument("--title", help="Use a different title from the file name")
    args = parser.parse_args()
    try:
        source = prepare(args.manuscript, args.name, args.title)
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({k: source[k] for k in ("slug", "title", "publishedAt", "images", "xPosts", "otherLinks")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
