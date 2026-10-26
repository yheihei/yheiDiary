#!/usr/bin/env python3
"""Create one yhei.dev EmDash draft from prepared private JSON.

The owner enters a PAT in a real Terminal. Credentials are never written or
printed, and an uncertain create result is never retried automatically.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
PRIVATE_DRAFTS = ROOT / "private/drafts"
CLI = ROOT / "site/node_modules/.bin/emdash"
SITE = "https://yhei.dev"
ACCESS_APP = SITE + "/_emdash/admin"
OWNER_EMAIL = "yheihei0126@gmail.com"
ACCESS_AUDIENCE = "e1746d72a727a25e7a6483fe433625de61294d91b7dda73a65cd2b7a87f68bfe"
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class Stop(Exception):
    pass


def read_prepared(path_arg: str, slug: str) -> tuple[Path, str]:
    if not SLUG_PATTERN.fullmatch(slug):
        raise Stop("slug は英小文字・数字・ハイフンのみで指定してください。")
    path = (ROOT / path_arg).resolve()
    if not path.is_relative_to(PRIVATE_DRAFTS.resolve()) or not path.is_file():
        raise Stop("原稿JSONはこのサイトの private/drafts 内の実在ファイルに限ります。")
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
    return path, data["title"]


def cached_access_jwt() -> str:
    try:
        result = subprocess.run(
            ["cloudflared", "access", "token", "-app", ACCESS_APP],
            capture_output=True, text=True, timeout=20, check=True,
        )
        jwt = result.stdout.strip()
        parts = jwt.split(".")
        if len(parts) != 3:
            raise Stop("既存のCloudflare Accessログインを確認できません。")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        audiences = payload.get("aud")
        if isinstance(audiences, str):
            audiences = [audiences]
        now = time.time()
        if (payload.get("email") != OWNER_EMAIL or payload.get("type") != "app"
                or not isinstance(audiences, list) or ACCESS_AUDIENCE not in audiences
                or not isinstance(payload.get("exp"), (int, float)) or payload["exp"] <= now + 60
                or not isinstance(payload.get("nbf"), (int, float)) or payload["nbf"] > now):
            raise Stop("Cloudflare Access認証の本人・対象・期限が一致しません。")
        return jwt
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        raise Stop("既存のCloudflare Accessログインを確認できません。") from exc


def cli_json(args: list[str], env: dict[str, str]) -> dict:
    try:
        response = subprocess.run(
            [str(CLI), *args, "--url", SITE, "--json"],
            cwd=ROOT / "site", env=env, capture_output=True, text=True, timeout=45,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise Stop("CLI結果が不明です。再投稿せず管理画面で確認してください。") from exc
    if response.returncode:
        raise Stop("CLIが停止しました。再投稿せず管理画面で確認してください。")
    try:
        data = json.loads(response.stdout)
    except ValueError as exc:
        raise Stop("CLI応答を検証できません。再投稿せず管理画面で確認してください。") from exc
    if not isinstance(data, dict) or "error" in data:
        raise Stop("CLI応答が想定外です。再投稿せず管理画面で確認してください。")
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


def create(path_arg: str, slug: str, secret_reader=getpass.getpass) -> str:
    path, title = read_prepared(path_arg, slug)
    if not CLI.is_file():
        raise Stop("このサイトのEmDash CLIが見つかりません。")
    if not sys.stdin.isatty():
        raise Stop("実際のTerminalで対話式に実行してください。")
    jwt = cached_access_jwt()
    pat = secret_reader("EmDash PAT を貼り付けて Enter（表示されません）: ").strip()
    if not pat:
        raise Stop("PATが入力されていません。")
    env = os.environ.copy()
    env["EMDASH_TOKEN"] = pat
    env["EMDASH_HEADERS"] = "Cf-Access-Token: " + jwt
    try:
        check_duplicate(title, slug, env)
        item = cli_json([
            "content", "create", "posts", "--file", str(path),
            "--slug", slug, "--draft",
        ], env)
        if not isinstance(item.get("id"), str) or not item["id"]:
            raise Stop("作成結果が不明です。再投稿せず管理画面で確認してください。")
        if item.get("status") == "published":
            raise Stop("公開状態の可能性があります。直ちに管理画面を確認してください。")
        return item["id"]
    finally:
        env.pop("EMDASH_TOKEN", None)
        env.pop("EMDASH_HEADERS", None)
        pat = ""
        jwt = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create exactly one yhei.dev EmDash draft")
    parser.add_argument("json_file", help="Prepared JSON inside private/drafts")
    parser.add_argument("slug", help="New post slug")
    args = parser.parse_args()
    try:
        item_id = create(args.json_file, args.slug)
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
