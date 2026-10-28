#!/usr/bin/env python3
"""Put the chosen eyecatch on the owner's public S3 bucket, once.

The object key is fixed by the image's content, diary/featured/<slug>-<sha16>.jpg,
so uploading the same image again is a no-op. The AWS CLI uses the owner's
own configured credentials; this script never reads or prints them. After the
upload, an anonymous GET must return the same bytes. The featured_image value
(provider external) is recorded in private/drafts/<slug>.source.json.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

from common import ROOT, Stop, load_sidecar, public_fetch, save_sidecar, sha256

BUCKET = "yhei-obsidian-images"
PUBLIC_BASE = f"https://{BUCKET}.s3.ap-northeast-1.amazonaws.com/"
PREFIX = "diary/featured/"
CACHE_CONTROL = "public, max-age=31536000, immutable"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def image_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                            capture_output=True, text=True, timeout=20)
    values = {}
    for line in result.stdout.splitlines()[1:]:
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()
    try:
        return int(values["pixelWidth"]), int(values["pixelHeight"])
    except (KeyError, ValueError) as exc:
        raise Stop("画像の寸法を読めません。") from exc


def aws(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["aws", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop("aws コマンドを実行できません。") from exc


def upload(slug: str, image_arg: str, alt: str) -> dict:
    source = load_sidecar(slug)
    image = (ROOT / image_arg).resolve()
    suffix = image.suffix.lower()
    if not image.is_file() or suffix not in MIME:
        raise Stop("アイキャッチは jpg・png・webp の実在ファイルを指定してください。")
    if not alt.strip():
        raise Stop("代替テキストを指定してください。")
    digest = sha256(image)
    width, height = image_size(image)
    mime = MIME[suffix]
    key = PREFIX + f"{slug}-{digest[:16]}" + (".jpg" if mime == "image/jpeg" else suffix)
    url = PUBLIC_BASE + key

    exists = aws(["s3api", "head-object", "--bucket", BUCKET, "--key", key]).returncode == 0
    if not exists:
        result = aws(["s3", "cp", str(image), f"s3://{BUCKET}/{key}", "--content-type", mime,
                      "--cache-control", CACHE_CONTROL, "--only-show-errors"])
        if result.returncode:
            raise Stop(f"S3 へのアップロードが失敗しました（終了コード {result.returncode}）。"
                       " aws の認証とバケットを確認してください。")

    status, ctype, body = public_fetch(url)
    if status != 200 or ctype != mime or hashlib.sha256(body).hexdigest() != digest:
        raise Stop(f"S3 の画像を未ログインで取得できないか、中身が違います（HTTP {status}）。"
                   " バケットの公開設定は変えずに本人に知らせてください。")

    source["eyecatch"] = {
        **{k: v for k, v in (source.get("eyecatch") or {}).items() if k == "candidates"},
        "file": str(image.relative_to(ROOT)) if image.is_relative_to(ROOT) else str(image),
        "sha256": digest,
        "alt": alt.strip(),
        "s3Key": key,
        "url": url,
        "featuredImage": {
            "provider": "external", "id": "", "src": url,
            "mimeType": mime, "width": width, "height": height, "alt": alt.strip(),
        },
    }
    save_sidecar(slug, source)
    return source["eyecatch"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload one eyecatch to the public S3 bucket")
    parser.add_argument("slug")
    parser.add_argument("image", help="Path relative to the repository root")
    parser.add_argument("--alt", required=True)
    args = parser.parse_args()
    try:
        eyecatch = upload(args.slug, args.image, args.alt)
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    print("S3 に置き、未ログインで同じ中身を取得できました: " + eyecatch["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
