#!/usr/bin/env python3
"""Publish one checked draft and give it the manuscript's date, once.

The publication date is 21:00 JST on the date in the manuscript's file name
(publishedAt in private/drafts/<slug>.source.json). It is set on the draft
first, and EmDash keeps an existing date when publishing. The draft's title,
body and eyecatch are checked before publishing and compared after. An
uncertain result is never retried.
"""
from __future__ import annotations

from datetime import datetime
import argparse
import sys

from common import (Stop, check_public_image, cli_json, credential_env, load_sidecar,
                    node_json, save_sidecar, SITE)


def same_instant(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return parse(a) == parse(b)


def read(post_id: str, env: dict[str, str], published: bool = False) -> dict:
    args = ["content", "get", "posts", post_id, "--raw"]
    return cli_json(args + ["--published"] if published else args, env)


def assert_item(item: dict, source: dict, status: str) -> None:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    if (item.get("id") != source["id"] or item.get("slug") != source["slug"]
            or item.get("status") != status or data.get("title") != source["title"]):
        raise Stop(f"記事ID・slug・題名・状態（{status} のはず）のどれかが想定と違います。")
    image = (source.get("eyecatch") or {}).get("featuredImage")
    if image and (data.get("featured_image") or {}).get("src") != image["src"]:
        raise Stop("下書きのアイキャッチが用意したものと違います。")


def set_date(item: dict, target: str, env: dict[str, str]) -> None:
    rev = item.get("_rev")
    if not isinstance(rev, str) or not rev:
        raise Stop("revision token を取得できません。")
    node_json("published_at.mjs", ["posts", item["id"], rev, target], env)


def publish(slug: str) -> str:
    source = load_sidecar(slug)
    if not source.get("id"):
        raise Stop("source.json に記事 ID がありません。先に create_draft.py を実行してください。")
    target = source.get("publishedAt")
    if not target:
        raise Stop("source.json に公開日がありません。")
    image = (source.get("eyecatch") or {}).get("featuredImage")
    if image:
        check_public_image(image)

    with credential_env() as env:
        draft = read(source["id"], env)
        assert_item(draft, source, "draft")
        body = draft["data"].get("content")
        if not same_instant(draft.get("publishedAt"), target):
            set_date(draft, target, env)
            draft = read(source["id"], env)
            assert_item(draft, source, "draft")
            if not same_instant(draft.get("publishedAt"), target):
                raise Stop("下書きの公開日を設定できません。公開せずに止めます。")

        cli_json(["content", "publish", "posts", source["id"]], env)
        live = read(source["id"], env, published=True)
        assert_item(live, source, "published")
        if not same_instant(live.get("publishedAt"), target):
            # EmDash keeps an existing date, but if it did not, fix it once on the live post.
            set_date(live, target, env)
            live = read(source["id"], env, published=True)
            assert_item(live, source, "published")
    if (live.get("draftRevisionId") is not None or live["data"].get("content") != body
            or not same_instant(live.get("publishedAt"), target)):
        raise Stop("公開後の記事を検証できません。やり直さず管理画面で確認してください。")

    url = f"{SITE}/posts/{slug}"
    source.update({"status": "published", "url": url, "publishApproved": True,
                   "publishedAtActual": live.get("publishedAt")})
    save_sidecar(slug, source)
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish one checked yhei.dev draft")
    parser.add_argument("slug")
    args = parser.parse_args()
    try:
        url = publish(args.slug)
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    print("公開しました: " + url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
