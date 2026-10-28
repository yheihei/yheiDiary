#!/usr/bin/env python3
"""Attach the uploaded eyecatch to one published post, keeping it published.

Reads the post with the official CLI, checks it is still the expected
published post with no pending draft, then sends one `content update` carrying
only featured_image. Without --draft the update publishes that one revision;
EmDash keeps the existing publication date. The title, body and date are
compared before and after. An uncertain result is never retried.
"""
from __future__ import annotations

import argparse
import json
import sys

from common import Stop, check_public_image, cli_json, credential_env, load_sidecar, save_sidecar


def read_published(post_id: str, env: dict[str, str]) -> dict:
    return cli_json(["content", "get", "posts", post_id, "--raw", "--published"], env)


def assert_post(item: dict, source: dict) -> None:
    if (item.get("id") != source["id"] or item.get("slug") != source["slug"]
            or item.get("status") != "published" or not isinstance(item.get("data"), dict)
            or item["data"].get("title") != source["title"]
            or item.get("draftRevisionId") is not None):
        raise Stop("記事ID・slug・題名・公開状態・未処理の下書きのどれかが想定と違います。変更しません。")


def attach(slug: str, replace: bool = False) -> str:
    source = load_sidecar(slug)
    if not source.get("id"):
        raise Stop("source.json に記事 ID がありません。")
    image = (source.get("eyecatch") or {}).get("featuredImage")
    if not image:
        raise Stop("アイキャッチがまだ上がっていません。先に upload_eyecatch.py を実行してください。")
    url = check_public_image(image)

    with credential_env() as env:
        before = read_published(source["id"], env)
        assert_post(before, source)
        current = before["data"].get("featured_image")
        if current and not replace:
            raise Stop("アイキャッチが既にあります。差し替えるなら --replace を付けてください。")
        rev = before.get("_rev")
        if not isinstance(rev, str) or not rev:
            raise Stop("revision token を取得できません。")
        others = {k: v for k, v in before["data"].items() if k != "featured_image"}
        payload = json.dumps({"featured_image": image}, ensure_ascii=False, separators=(",", ":"))
        cli_json(["content", "update", "posts", source["id"], "--rev", rev, "--data", payload], env)
        after = read_published(source["id"], env)

    assert_post(after, source)
    attached = after["data"].get("featured_image") or {}
    if (attached.get("src") != image["src"]
            or {k: v for k, v in after["data"].items() if k != "featured_image"} != others
            or after.get("publishedAt") != before.get("publishedAt")):
        raise Stop("更新後の記事を検証できません。やり直さず管理画面で確認してください。")
    source["status"] = "published"
    source["eyecatch"]["attachedAt"] = after.get("updatedAt")
    save_sidecar(slug, source)
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach the eyecatch to one published yhei.dev post")
    parser.add_argument("slug")
    parser.add_argument("--replace", action="store_true", help="Replace an existing eyecatch")
    args = parser.parse_args()
    try:
        url = attach(args.slug, args.replace)
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    print("公開のままアイキャッチだけを付けました: " + url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
