#!/usr/bin/env python3
"""Generate eyecatch candidates with Gemini (Nano Banana 2), one per prompt file.

Reads private/drafts/<slug>/eyecatch/*.prompt.md and makes one 16:9 1K image
for each, in parallel, through the generator in the edit-youtube-video skill.
That generator reads GEMINI_API_KEY itself, from the environment or its own
scripts/.env; this script never touches the key.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from common import PRIVATE_DRAFTS, ROOT, Stop, load_sidecar, save_sidecar

GENERATOR = Path(os.environ.get(
    "YHEI_THUMBNAIL_SCRIPT",
    Path.home() / ".agents/skills/edit-youtube-video/scripts/thumbnail.mjs",
))
IMAGE_SUFFIXES = {".jpg", ".png", ".webp"}


def eyecatch_dir(slug: str) -> Path:
    return PRIVATE_DRAFTS / slug / "eyecatch"


def generate(slug: str) -> list[Path]:
    source = load_sidecar(slug)
    folder = eyecatch_dir(slug)
    prompts = sorted(folder.glob("*.prompt.md"))
    if not 1 <= len(prompts) <= 3:
        raise Stop(f"{folder.relative_to(ROOT)} に *.prompt.md を1〜3個置いてください。")
    if not GENERATOR.is_file():
        raise Stop("画像の生成スクリプトが見つかりません: " + str(GENERATOR))
    before = {p for p in folder.iterdir() if p.suffix in IMAGE_SUFFIXES}

    jobs = []
    for prompt in prompts:
        name = prompt.name.removesuffix(".prompt.md")
        jobs.append(subprocess.Popen(
            ["node", str(GENERATOR), "generate", "--prompt", str(prompt), "--out", str(folder),
             "--name", name, "--n", "1", "--size", "1K", "--aspect", "16:9"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        ))
    failed = 0
    for job in jobs:
        output, _ = job.communicate(timeout=600)
        print(output.strip())
        failed += job.returncode != 0

    made = sorted(p for p in folder.iterdir() if p.suffix in IMAGE_SUFFIXES and p not in before)
    eyecatch = source.setdefault("eyecatch", {})
    eyecatch["candidates"] = sorted({*eyecatch.get("candidates", []),
                                     *(str(p.relative_to(ROOT)) for p in made)})
    save_sidecar(slug, source)
    if failed:
        raise Stop(f"{failed}枚の生成に失敗しました。上の表示を見てください。")
    return made


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate eyecatch candidates for one diary post")
    parser.add_argument("slug")
    args = parser.parse_args()
    try:
        made = generate(args.slug)
    except Stop as exc:
        print("停止: " + str(exc), file=sys.stderr)
        return 1
    print("候補:")
    for path in made:
        print("  " + str(path.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
