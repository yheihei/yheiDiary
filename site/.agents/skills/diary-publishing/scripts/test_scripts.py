"""Offline tests for the diary-publishing scripts. Nothing here reaches production.

Run: python3 site/.agents/skills/diary-publishing/scripts/test_scripts.py
"""
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import attach_eyecatch  # noqa: E402
import common  # noqa: E402
import create_draft  # noqa: E402
import make_eyecatch  # noqa: E402
import prepare_post  # noqa: E402
import publish_post  # noqa: E402

SLUG = "20261027-test-post"
IMAGE = {"provider": "external", "id": "", "src": "https://example.com/a.jpg",
         "mimeType": "image/jpeg", "width": 1376, "height": 768, "alt": "絵"}


@contextlib.contextmanager
def fake_env():
    yield {"EMDASH_TOKEN": "dummy-secret"}


class Sandbox(unittest.TestCase):
    """Point every script at a temporary private/drafts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.drafts = self.root / "private/drafts"
        self.drafts.mkdir(parents=True)
        self.patches = [patch.object(m, "PRIVATE_DRAFTS", self.drafts)
                        for m in (common, create_draft, make_eyecatch, prepare_post) if hasattr(m, "PRIVATE_DRAFTS")]
        self.patches += [patch.object(m, "ROOT", self.root) for m in (common, make_eyecatch, prepare_post)]
        for m in (create_draft, attach_eyecatch, publish_post):
            self.patches.append(patch.object(m, "credential_env", fake_env))
            self.patches.append(patch.object(m, "check_public_image", lambda image: image["src"]))
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def manuscript(self, body: str, name: str = "20261027 - テスト.md") -> Path:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return path


class PrepareTests(Sandbox):
    def test_writes_post_and_sidecar_with_2100_jst(self):
        path = self.manuscript("---\ndate created: x\n---\n\n一段落目。\n\nhttps://x.com/a/status/123\n\n二段落目。")
        source = prepare_post.prepare(str(path), "test-post")
        post = json.loads((self.drafts / f"{SLUG}.post.json").read_text())
        self.assertEqual(post["title"], "テスト")
        self.assertIn("https://x.com/a/status/123\n", post["content"])
        self.assertNotIn("date created", post["content"])
        self.assertEqual(source["publishedAt"], "2026-10-27T21:00:00+09:00")
        self.assertEqual(source["xPosts"], ["https://x.com/a/status/123"])
        self.assertEqual((self.drafts / f"{SLUG}.post.json").stat().st_mode & 0o777, 0o600)

    def test_local_image_stops(self):
        path = self.manuscript("本文\n\n![[pasted.png]]\n")
        with self.assertRaises(common.Stop):
            prepare_post.prepare(str(path), "test-post")

    def test_created_post_is_not_prepared_again(self):
        common.save_sidecar(SLUG, {"id": "01ABC"})
        with self.assertRaises(common.Stop):
            prepare_post.prepare(str(self.manuscript("本文")), "test-post")


class EyecatchTests(Sandbox):
    def test_one_image_per_prompt_is_recorded(self):
        common.save_sidecar(SLUG, {"slug": SLUG})
        folder = self.drafts / SLUG / "eyecatch"
        folder.mkdir(parents=True)
        for name in "abc":
            (folder / f"{name}.prompt.md").write_text("prompt")
        fake = self.root / "fake.mjs"
        fake.write_text(
            "import fs from 'node:fs';\n"
            "const a = process.argv;\n"
            "const out = a[a.indexOf('--out') + 1], name = a[a.indexOf('--name') + 1];\n"
            "fs.writeFileSync(`${out}/${name}-1.jpg`, 'x');\n"
            "console.log(`${name}-1.jpg made`);\n")
        with patch.object(make_eyecatch, "GENERATOR", fake):
            made = make_eyecatch.generate(SLUG)
        self.assertEqual([p.name for p in made], ["a-1.jpg", "b-1.jpg", "c-1.jpg"])
        self.assertEqual(len(common.load_sidecar(SLUG)["eyecatch"]["candidates"]), 3)


class CreateTests(Sandbox):
    def prepared(self, eyecatch=True):
        common.write_private(self.drafts / f"{SLUG}.post.json",
                             json.dumps({"title": "テスト", "content": "本文\n"}, ensure_ascii=False))
        common.save_sidecar(SLUG, {"slug": SLUG, "title": "テスト",
                                   **({"eyecatch": {"featuredImage": IMAGE}} if eyecatch else {})})

    def test_creates_draft_with_eyecatch_once(self):
        self.prepared()
        calls = []

        def cli(args, env, timeout=45, stdin=None):
            calls.append((args, stdin))
            if args[:2] == ["content", "list"]:
                return {"items": [{"slug": "other", "title": "別"}]}
            return {"id": "01NEW", "status": "draft"}

        with patch.object(create_draft, "cli_json", cli):
            self.assertEqual(create_draft.create(SLUG), "01NEW")
        args, stdin = calls[-1]
        self.assertIn("--draft", args)
        self.assertEqual(json.loads(stdin)["featured_image"], IMAGE)
        self.assertEqual(common.load_sidecar(SLUG)["id"], "01NEW")

    def test_duplicate_or_missing_eyecatch_stops(self):
        self.prepared(eyecatch=False)
        with self.assertRaises(common.Stop):
            create_draft.create(SLUG)
        self.prepared()
        with patch.object(create_draft, "cli_json",
                          lambda *a, **k: {"items": [{"slug": SLUG, "title": "テスト"}]}):
            with self.assertRaises(common.Stop):
                create_draft.create(SLUG)


class PublishTests(Sandbox):
    def test_sets_date_on_draft_then_publishes(self):
        common.save_sidecar(SLUG, {"id": "01NEW", "slug": SLUG, "title": "テスト",
                                   "publishedAt": "2026-10-27T21:00:00+09:00",
                                   "eyecatch": {"featuredImage": IMAGE}})
        state = {"status": "draft", "publishedAt": None}
        calls = []

        def item():
            return {"id": "01NEW", "slug": SLUG, "_rev": "r", "draftRevisionId": None,
                    "data": {"title": "テスト", "content": [], "featured_image": IMAGE}, **state}

        def cli(args, env, timeout=45, stdin=None):
            calls.append(args[:2])
            if args[:2] == ["content", "publish"]:
                state["status"] = "published"
            return item()

        def node(script, args, env, timeout=60):
            calls.append(["put", args[3]])
            state["publishedAt"] = "2026-10-27T12:00:00.000Z"
            return {"ok": True}

        with patch.object(publish_post, "cli_json", cli), patch.object(publish_post, "node_json", node):
            url = publish_post.publish(SLUG)
        self.assertEqual(url, "https://yhei.dev/posts/" + SLUG)
        order = [c[0] for c in calls]
        self.assertLess(order.index("put"), calls.index(["content", "publish"]))
        self.assertEqual(common.load_sidecar(SLUG)["status"], "published")


class AttachTests(Sandbox):
    def test_only_featured_image_is_sent(self):
        common.save_sidecar(SLUG, {"id": "01OLD", "slug": SLUG, "title": "テスト",
                                   "eyecatch": {"featuredImage": IMAGE}})
        state = {"featured_image": None}
        sent = []

        def cli(args, env, timeout=45, stdin=None):
            if args[:2] == ["content", "update"]:
                sent.append(json.loads(args[args.index("--data") + 1]))
                state["featured_image"] = IMAGE
            return {"id": "01OLD", "slug": SLUG, "status": "published", "_rev": "r",
                    "draftRevisionId": None, "publishedAt": "2026-10-27T12:00:00.000Z",
                    "data": {"title": "テスト", "content": [], **state}}

        with patch.object(attach_eyecatch, "cli_json", cli):
            attach_eyecatch.attach(SLUG)
        self.assertEqual(sent, [{"featured_image": IMAGE}])

    def test_existing_eyecatch_is_kept_without_replace(self):
        common.save_sidecar(SLUG, {"id": "01OLD", "slug": SLUG, "title": "テスト",
                                   "eyecatch": {"featuredImage": IMAGE}})
        published = {"id": "01OLD", "slug": SLUG, "status": "published", "_rev": "r",
                     "draftRevisionId": None, "data": {"title": "テスト", "featured_image": {"src": "x"}}}
        with patch.object(attach_eyecatch, "cli_json", lambda *a, **k: published):
            with self.assertRaises(common.Stop):
                attach_eyecatch.attach(SLUG)


class SecretTests(unittest.TestCase):
    def test_cli_failure_does_not_echo_output(self):
        class Result:
            returncode = 1
            stdout = "dummy-secret"
            stderr = "HTTP 403 dummy-secret"
        with patch.object(common.subprocess, "run", return_value=Result()):
            with self.assertRaises(common.Stop) as result:
                common.cli_json(["content", "get"], {})
        self.assertNotIn("dummy-secret", str(result.exception))
        self.assertIn("403", str(result.exception))


if __name__ == "__main__":
    unittest.main()
