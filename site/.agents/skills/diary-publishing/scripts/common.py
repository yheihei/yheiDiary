"""Shared helpers for the yhei.dev diary-publishing scripts.

The EmDash PAT comes from EMDASH_PAT in the gitignored .env at the repository
root, or, when that is empty, from hidden input in a real Terminal. The Access
JWT comes from the owner's existing cloudflared login. Both reach child
processes only through their environment and are never written or printed.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
SITE_DIR = ROOT / "site"
PRIVATE_DRAFTS = ROOT / "private/drafts"
CLI = SITE_DIR / "node_modules/.bin/emdash"
SCRIPTS = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_KEY = "EMDASH_PAT"
SITE = "https://yhei.dev"
ACCESS_APP = SITE + "/_emdash/admin"
OWNER_EMAIL = "yheihei0126@gmail.com"
ACCESS_AUDIENCE = "e1746d72a727a25e7a6483fe433625de61294d91b7dda73a65cd2b7a87f68bfe"
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MEDIA_FILE_PATH = "/_emdash/api/media/file/"


class Stop(Exception):
    pass


def env_file_pat() -> str:
    """Return EMDASH_PAT from the repository root .env, or "" when it is not set."""
    if not ENV_FILE.is_file():
        return ""
    if ENV_FILE.stat().st_mode & 0o077:
        raise Stop(".env の権限を 0600 にしてください。")
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Stop(".env を読めません。") from exc
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip().removeprefix("export ").strip() == ENV_KEY:
            return value.strip().strip("\"'")
    return ""


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
        raise Stop("既存のCloudflare Accessログインを確認できません。"
                   " cloudflared access login " + ACCESS_APP + " を1回実行してください。") from exc


@contextmanager
def credential_env(secret_reader=getpass.getpass):
    """Yield a child-process environment carrying the PAT and the Access JWT."""
    if not CLI.is_file():
        raise Stop("このサイトのEmDash CLIが見つかりません。")
    jwt = cached_access_jwt()
    pat = env_file_pat()
    if not pat:
        if not sys.stdin.isatty():
            raise Stop(".env の EMDASH_PAT が空です。実際のTerminalで対話式に実行してください。")
        pat = secret_reader("EmDash PAT を貼り付けて Enter（表示されません）: ").strip()
    if not pat:
        raise Stop("PATが入力されていません。")
    env = os.environ.copy()
    env["EMDASH_TOKEN"] = pat
    env["EMDASH_HEADERS"] = "Cf-Access-Token: " + jwt
    pat = jwt = ""
    try:
        yield env
    finally:
        env.pop("EMDASH_TOKEN", None)
        env.pop("EMDASH_HEADERS", None)


def describe_failure(stderr: str) -> str:
    """Name the kind of CLI failure without echoing output that could hold secrets."""
    if re.search(r"\b403\b|forbidden|insufficient|scope|permission", stderr, re.I):
        return "権限が足りません（403）。PAT の権限を確認してください。"
    if re.search(r"\b401\b|unauthori[sz]ed", stderr, re.I):
        return "PAT が無効か期限切れです（401）。"
    if re.search(r"\b409\b|conflict", stderr, re.I):
        return "記事がほかで更新されています（409）。読み直してから考えてください。"
    if re.search(r"1010|cloudflareaccess|\b302\b", stderr, re.I):
        return "Cloudflare で止まりました。Access のログインを確認してください。"
    return "CLIが停止しました。"


def cli_json(args: list[str], env: dict[str, str], timeout: int = 45, stdin: str | None = None) -> dict:
    try:
        response = subprocess.run(
            [str(CLI), *args, "--url", SITE, "--json"], input=stdin,
            cwd=SITE_DIR, env=env, capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise Stop("CLI結果が不明です。やり直さず管理画面で確認してください。") from exc
    if response.returncode:
        raise Stop(describe_failure(response.stderr + response.stdout)
                   + " やり直さず管理画面で確認してください。")
    try:
        data = json.loads(response.stdout)
    except ValueError as exc:
        raise Stop("CLI応答を検証できません。やり直さず管理画面で確認してください。") from exc
    if not isinstance(data, dict) or "error" in data:
        raise Stop("CLI応答が想定外です。やり直さず管理画面で確認してください。")
    return data


def node_json(script: str, args: list[str], env: dict[str, str], timeout: int = 60) -> dict:
    """Run one of the .mjs helpers next to this file; it prints one JSON object."""
    try:
        result = subprocess.run(
            ["node", str(SCRIPTS / script), *args],
            cwd=SITE_DIR, env=env, capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise Stop("結果が不明です。やり直さず管理画面で確認してください。") from exc
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise Stop("応答を検証できません。やり直さず管理画面で確認してください。") from exc
    if result.returncode or not isinstance(data, dict) or "error" in data:
        raise Stop(describe_failure(json.dumps(data.get("error", ""), ensure_ascii=False)
                                    if isinstance(data, dict) else "")
                   + " やり直さず管理画面で確認してください。")
    return data


def check_slug(slug: str) -> None:
    if not SLUG_PATTERN.fullmatch(slug):
        raise Stop("slug は英小文字・数字・ハイフンのみで指定してください。")


def sidecar_path(slug: str) -> Path:
    check_slug(slug)
    return PRIVATE_DRAFTS / (slug + ".source.json")


def load_sidecar(slug: str) -> dict:
    path = sidecar_path(slug)
    if not path.is_file():
        raise Stop(f"{path.relative_to(ROOT)} がありません。先に prepare_post.py を実行してください。")
    return json.loads(path.read_text(encoding="utf-8"))


def save_sidecar(slug: str, data: dict) -> None:
    write_private(sidecar_path(slug), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_fetch(url: str, max_bytes: int = 20_000_000) -> tuple[int, str, bytes]:
    """GET a public URL with no credentials. Returns (status, content type, body)."""
    try:
        result = subprocess.run(
            ["curl", "-sS", "--max-time", "30", "--max-filesize", str(max_bytes),
             "--proto", "=https", "-o", "-", "-w", "\n%{http_code} %{content_type}", url],
            capture_output=True, timeout=40,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop("公開URLを取得できません: " + url) from exc
    body, _, tail = result.stdout.rpartition(b"\n")
    status, _, ctype = tail.decode("ascii", "replace").partition(" ")
    return int(status or 0), ctype, body


def featured_image_url(image: dict) -> str:
    """The URL the post page renders for a featured_image value."""
    src = image.get("src")
    if isinstance(src, str) and src:
        return src if src.startswith("http") else SITE + src
    meta = image.get("meta") if isinstance(image.get("meta"), dict) else {}
    key = meta.get("storageKey") or image.get("id")
    return SITE + MEDIA_FILE_PATH + key if key else ""


def check_public_image(image: dict) -> str:
    """Stop unless anonymous visitors can load the featured image."""
    url = featured_image_url(image)
    status, ctype, _ = public_fetch(url) if url else (0, "", b"")
    if status != 200 or not ctype.startswith("image/"):
        raise Stop(f"アイキャッチを未ログインで取得できません（HTTP {status}）。"
                   " 記事には付けません。SKILL.md の「3. S3 に置く」を見てください。")
    return url
