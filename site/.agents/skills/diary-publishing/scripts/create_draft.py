#!/usr/bin/env python3
"""Create one yhei.dev EmDash draft from the prepared private JSON.

Reads private/drafts/<slug>.post.json and, when an eyecatch has been uploaded,
its featured_image from private/drafts/<slug>.source.json. The eyecatch is
attached only when anonymous visitors can load it. An uncertain create result
is never retried automatically.
"""
from __future__ import annotations

import argparse
import json
import sys

from common import (PRIVATE_DRAFTS, Stop, check_public_image, check_slug, cli_json,
                    credential_env, load_sidecar, save_sidecar)


def read_prepared(slug: str) -> dict:
    check_slug(slug)
    path = PRIVATE_DRAFTS / (slug + ".post.json")
    if not path.is_file():
        raise Stop(f"private/drafts/{slug}.post.json がありません。先に prepare_post.py を実行してください。")
    if path.stat().st_mode & 0o077:
        raise Stop("原稿JSONの権限を 0600 にしてください。")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Stop("原稿JSONを読めません。") from exc
    if (not isinstance(data, dict) or set(data) != {"title", "content"}
            or not isinstance(data["title"], str) or not data["title"].strip()
            or not isinstance(data["content"], str) or not data["content"].strip()):
        raise Stop("原稿JSONには空でない title と content だけを指定してください。")
    if data["title"].strip() != data["title"]:
        raise Stop("タイトル前後の空白を確認してください。")
    return data


def check_duplicate(title: str, slug: str, env: dict[str, str]) -> None:
    cursor = None
    seen = set()
    for _ in range(30):
        args = ["content", "list", "posts", "--limit", "100"]
        if cursor:
            args += ["--cursor", cursor]
        page = cli_json(args, env)
        if not isinstance(page.get("items"), list):
            raise Stop("記事一覧を検証できません。")
        for item in page["items"]:
            if not isinstance(item, dict):
                raise Stop("記事一覧を検証できません。")
            if item.get("slug") == slug or item.get("title") == title:
                raise Stop("同じslugまたは題名の記事があります。新規作成しません。")
        cursor = page.get("nextCursor")
        if not cursor:
            return
        if not isinstance(cursor, str) or cursor in seen:
            raise Stop("記事一覧の続きが不明です。")
        seen.add(cursor)
    raise Stop("記事一覧の確認を完了できません。")


def create(slug: str, without_eyecatch: bool = False) -> str:
    data = read_prepared(slug)
    source = load_sidecar(slug)
    if source.get("id"):
        raise Stop("この slug の記事は作成済みです。記事 ID " + source["id"])
    image = (source.get("eyecatch") or {}).get("featuredImage")
    if image and not without_eyecatch:
        check_public_image(image)
        data["featured_image"] = image
    elif not image and not without_eyecatch:
        raise Stop("アイキャッチがまだありません。付けずに作るなら --without-eyecatch を付けてください。")

    with credential_env() as env:
        check_duplicate(data["title"], slug, env)
        item = cli_json(["content", "create", "posts", "--stdin", "--slug", slug, "--draft"],
                        env, timeout=60, stdin=json.dumps(data, ensure_ascii=False))
    if not isinstance(item.get("id"), str) or not item["id"]:
        raise Stop("作成結果が不明です。再投稿せず管理画面で確認してください。")
    source.update({"id": item["id"], "status": item.get("status")})
    save_sidecar(slug, source)
    if item.get("status") == "published":
        raise Stop("公開状態の可能性があります。直ちに管理画面を確認してください。")
    return item["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create exactly one yhei.dev EmDash draft")
    parser.add_argument("slug", help="Slug prepared by prepare_post.py")
    parser.add_argument("--without-eyecatch", action="store_true",
                        help="Create the draft even though no eyecatch is attached")
    args = parser.parse_args()
    try:
        item_id = create(args.slug, args.without_eyecatch)
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("停止: 想定外のエラーです。再投稿せず管理画面で確認してください。", file=sys.stderr)
        return 1
    print("下書きを作成しました。記事 ID: " + item_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
