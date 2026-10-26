#!/usr/bin/env python3
"""Set the approved cover on one published yhei.dev post; owner enters PAT invisibly.

This is intentionally single-use. A failed or uncertain write is never retried.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path("/Users/yhei/emdash/diary")
SITE = "https://yhei.dev"
POST_ID = "01M5VY0SR55P9BNS7DK89B5YSB"
SLUG = "20261025-wordpress-to-emdash"
TITLE = "WordPressをEmDashへ移行"
IMAGE = ROOT / "private/design-candidates-2026-10-26/wordpress-to-emdash-3.jpg"
IMAGE_SHA256 = "67cb0a1a78b4fb9e8f782e597dd33a2c931e0a375df9b29983460a9e18863ef0"
IMAGE_URL = SITE + "/featured/wordpress-to-emdash-67cb0a1a78b4fb9e.jpg"
CLI = ROOT / "site/node_modules/.bin/emdash"
ALT = "積み重ねた日記をWordPressからEmDashへ移すイメージ"


class Stop(Exception):
    pass


def verify_public_image() -> None:
    if not IMAGE.is_file() or hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA256:
        raise Stop("採用したローカル画像の一致を確認できません。")
    try:
        result = subprocess.run(
            ["curl", "-fSsL", "--max-time", "20", "--max-filesize", "2000000",
             "--proto", "=https", "--proto-redir", "=https", IMAGE_URL],
            capture_output=True, timeout=25,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop("公開画像を取得できません。記事は変更しません。") from exc
    if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != IMAGE_SHA256:
        raise Stop("公開画像の内容が採用画像と一致しません。")


def cli_json(args: list[str], env: dict[str, str]) -> dict:
    try:
        result = subprocess.run(
            [str(CLI), *args, "--url", SITE, "--json"],
            cwd=ROOT / "site", env=env, capture_output=True, text=True, timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop("CLI結果が不明です。再実行せず管理画面で状態確認してください。") from exc
    if result.returncode != 0:
        # Do not echo CLI output: a proxy response might contain credentials.
        raise Stop("CLIが停止しました。再実行せず管理画面で状態確認してください。")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise Stop("CLI応答が不明です。再実行せず管理画面で状態確認してください。") from exc
    if not isinstance(value, dict) or "error" in value:
        raise Stop("CLI応答を検証できません。再実行せず状態確認してください。")
    return value


def assert_post(item: dict) -> None:
    if (item.get("id") != POST_ID or item.get("slug") != SLUG
            or item.get("status") != "published" or not isinstance(item.get("data"), dict)
            or item["data"].get("title") != TITLE
            or item.get("draftRevisionId") is not None):
        raise Stop("記事ID・slug・公開状態・未処理下書きの検査に失敗しました。")


def run() -> None:
    if not sys.stdin.isatty() or not CLI.is_file():
        raise Stop("Mac miniの対話式Terminalと既存公式CLIが必要です。")
    verify_public_image()
    # Reuse the approved, in-memory validation of the owner's Access JWT.
    from post_diary_draft import access_jwt
    jwt = access_jwt()
    pat = getpass.getpass("既存の3権限EmDash PATを貼り付けてEnter（表示されません）: ").strip()
    if not pat:
        raise Stop("PATが入力されていません。")
    env = os.environ.copy()
    env.pop("EMDASH_TOKEN", None)
    env.pop("EMDASH_HEADERS", None)
    env["EMDASH_TOKEN"] = pat
    env["EMDASH_HEADERS"] = "Cf-Access-Token: " + jwt
    try:
        before = cli_json(["content", "get", "posts", POST_ID, "--raw", "--published"], env)
        assert_post(before)
        image_before = before["data"].get("featured_image")
        if image_before is not None:
            raise Stop("アイキャッチが既にあります。上書きしません。")
        rev = before.get("_rev")
        if not isinstance(rev, str) or not rev:
            raise Stop("必須のrevision tokenを取得できません。")
        other_data = {k: v for k, v in before["data"].items() if k != "featured_image"}
        image_value = {
            "provider": "external", "id": "", "src": IMAGE_URL,
            "mimeType": "image/jpeg", "width": 1376, "height": 768, "alt": ALT,
        }
        payload = json.dumps({"featured_image": image_value}, ensure_ascii=False, separators=(",", ":"))
        # No --draft: EmDash's official update command publishes this one revision.
        cli_json(["content", "update", "posts", POST_ID, "--rev", rev, "--data", payload], env)
        after = cli_json(["content", "get", "posts", POST_ID, "--raw", "--published"], env)
        assert_post(after)
        if (after["data"].get("featured_image", {}).get("src") != IMAGE_URL
                or {k: v for k, v in after["data"].items() if k != "featured_image"} != other_data):
            raise Stop("更新後の記事内容を検証できません。再実行せず管理画面で確認してください。")
        print("確認済み: 指定記事のアイキャッチのみ公開。" + SITE + "/posts/" + SLUG)
    finally:
        env.pop("EMDASH_TOKEN", None)
        env.pop("EMDASH_HEADERS", None)
        pat = ""
        jwt = ""


if __name__ == "__main__":
    try:
        run()
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("停止: 未知の結果です。再実行せず管理画面で状態確認してください。", file=sys.stderr)
        sys.exit(1)
