#!/usr/bin/env python3
"""Create one EmDash draft using owner-entered PAT and cached Cloudflare Access.

No PAT is persisted, echoed, or placed in argv. On an uncertain result, stop.
"""
from __future__ import annotations

import base64
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SITE = "https://yhei.dev"
ACCESS_APP = SITE + "/_emdash/admin"
COLLECTION = "posts"
SLUG = "20261025-wordpress-to-emdash"
ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "private/drafts/20261025-wordpress-to-emdash.post.json"
CLI = ROOT / "site/node_modules/.bin/emdash"
EXPECTED_TITLE = "WordPressをEmDashへ移行"
EXPECTED_EMAIL = "yheihei0126@gmail.com"
EXPECTED_ACCESS_AUDIENCE = "e1746d72a727a25e7a6483fe433625de61294d91b7dda73a65cd2b7a87f68bfe"


class Stop(Exception):
    pass


def access_jwt() -> str:
    try:
        result = subprocess.run(
            ["cloudflared", "access", "token", "-app", ACCESS_APP],
            capture_output=True, text=True, timeout=20, check=True,
        )
        token = result.stdout.strip()
        parts = token.split(".")
        if len(parts) != 3:
            raise Stop("Cloudflare Access 認証が確認できません。")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        audiences = payload.get("aud")
        if isinstance(audiences, str):
            audiences = [audiences]
        now = time.time()
        if (payload.get("email") != EXPECTED_EMAIL or payload.get("type") != "app"
                or not isinstance(audiences, list) or EXPECTED_ACCESS_AUDIENCE not in audiences
                or not isinstance(payload.get("exp"), (int, float)) or payload["exp"] <= now + 60
                or not isinstance(payload.get("nbf"), (int, float)) or payload["nbf"] > now):
            raise Stop("Cloudflare Access の本人認証が一致しないか期限切れです。")
        return token
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        raise Stop("Cloudflare Access の既存ログインを確認できません。") from exc


def cli_json(args: list[str], env: dict[str, str]) -> dict:
    try:
        result = subprocess.run(
            [str(CLI), *args, "--url", SITE, "--json"],
            cwd=ROOT / "site", env=env, capture_output=True, text=True, timeout=45,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise Stop("CLI の結果が不明です。再投入せず状態確認が必要です。") from exc
    if result.returncode != 0:
        # CLI diagnostics might contain sensitive response details; never echo them.
        raise Stop("CLI が停止しました。再投入せず状態確認が必要です。")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise Stop("CLI 応答を検証できません。再投入せず状態確認が必要です。") from exc
    if not isinstance(value, dict) or "error" in value:
        raise Stop("CLI 応答が予期した形ではありません。再投入せず状態確認が必要です。")
    return value


def ensure_not_duplicate(env: dict[str, str]) -> None:
    cursor = None
    seen = set()
    for _ in range(30):
        args = ["content", "list", COLLECTION, "--limit", "100"]
        if cursor:
            args += ["--cursor", cursor]
        page = cli_json(args, env)
        items = page.get("items")
        if not isinstance(items, list):
            raise Stop("既存記事の一覧を検証できません。")
        for item in items:
            if not isinstance(item, dict):
                raise Stop("既存記事の一覧を検証できません。")
            if item.get("slug") == SLUG or item.get("title") == EXPECTED_TITLE:
                raise Stop("同じ slug または題名の記事が既にあります。作成しません。")
        cursor = page.get("nextCursor")
        if not cursor:
            return
        if not isinstance(cursor, str) or cursor in seen:
            raise Stop("記事一覧の続きを検証できません。")
        seen.add(cursor)
    raise Stop("記事一覧が上限内で完了しません。")


def perform(get_secret=getpass.getpass) -> str:
    if not CLI.is_file() or not DRAFT.is_file():
        raise Stop("固定した CLI または原稿 JSON が見つかりません。")
    data = json.loads(DRAFT.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("title") != EXPECTED_TITLE or not isinstance(data.get("content"), str):
        raise Stop("原稿 JSON が想定と異なります。")
    if not sys.stdin.isatty():
        raise Stop("対話式 Terminal で実行してください。")
    jwt = access_jwt()
    secret = get_secret("本人が発行した EmDash PAT を貼り付けて Enter（表示されません）: ").strip()
    if not secret:
        raise Stop("PAT が入力されていません。")
    env = os.environ.copy()
    env.pop("EMDASH_TOKEN", None)
    env.pop("EMDASH_HEADERS", None)
    env["EMDASH_TOKEN"] = secret
    env["EMDASH_HEADERS"] = "Cf-Access-Token: " + jwt
    try:
        ensure_not_duplicate(env)
        result = cli_json([
            "content", "create", COLLECTION, "--file", str(DRAFT),
            "--slug", SLUG, "--draft",
        ], env)
        item_id = result.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise Stop("作成結果が不明です。再投入せず状態確認が必要です。")
        if result.get("status") == "published":
            raise Stop("作成結果が公開状態です。すぐに状態確認が必要です。")
        return item_id
    finally:
        env.pop("EMDASH_TOKEN", None)
        env.pop("EMDASH_HEADERS", None)
        secret = ""
        jwt = ""


def main() -> int:
    try:
        item_id = perform()
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("停止: 想定外のエラーです。再投入せず状態確認が必要です。", file=sys.stderr)
        return 1
    print("下書きを作成しました。記事 ID: " + item_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
