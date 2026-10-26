import contextlib
import io
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, "/Users/yhei/emdash/diary/site/scripts")
import update_wordpress_cover as cover


class CoverGuardTests(unittest.TestCase):
    def test_wrong_article_or_pending_draft_stops(self):
        base = {"id": cover.POST_ID, "slug": cover.SLUG, "status": "published",
                "draftRevisionId": None, "data": {"title": cover.TITLE}}
        cover.assert_post(base)
        for key, value in [("id", "other"), ("status", "draft"),
                           ("draftRevisionId", "pending")]:
            wrong = {**base, key: value}
            with self.assertRaises(cover.Stop):
                cover.assert_post(wrong)

    def test_public_image_failure_before_secret_prompt(self):
        called = []
        with patch.object(cover.sys.stdin, "isatty", return_value=True), \
             patch.object(cover, "verify_public_image", side_effect=cover.Stop("missing")), \
             patch.object(cover.getpass, "getpass", side_effect=lambda _: called.append(True)):
            with self.assertRaises(cover.Stop):
                cover.run()
        self.assertFalse(called)

    def test_cli_failure_does_not_echo_output(self):
        class Result:
            returncode = 1
            stdout = "dummy-secret"
            stderr = "dummy-secret"
        with patch.object(cover.subprocess, "run", return_value=Result()):
            with self.assertRaises(cover.Stop) as result:
                cover.cli_json(["content", "get"], {})
        self.assertNotIn("dummy-secret", str(result.exception))

    def test_one_field_update_with_dummy_secret(self):
        before = {"id": cover.POST_ID, "slug": cover.SLUG, "status": "published",
                  "draftRevisionId": None, "_rev": "dummy-rev",
                  "data": {"title": cover.TITLE, "content": [{"_type": "block", "text": "unchanged"}],
                           "featured_image": None}}
        after = {**before, "data": {**before["data"], "featured_image": {
            "provider": "external", "id": "", "src": cover.IMAGE_URL}}}
        calls = []
        def fake_cli(args, env):
            self.assertEqual(env.get("EMDASH_TOKEN"), "dummy-secret")
            self.assertEqual(env.get("EMDASH_HEADERS"), "Cf-Access-Token: dummy-jwt")
            calls.append(args)
            return before if len(calls) == 1 else after
        fake_auth = types.ModuleType("post_diary_draft")
        fake_auth.access_jwt = lambda: "dummy-jwt"
        capture = io.StringIO()
        with patch.object(cover.sys.stdin, "isatty", return_value=True), \
             patch.object(cover, "verify_public_image"), \
             patch.object(cover.getpass, "getpass", return_value="dummy-secret"), \
             patch.dict(sys.modules, {"post_diary_draft": fake_auth}), \
             patch.object(cover, "cli_json", side_effect=fake_cli), \
             contextlib.redirect_stdout(capture):
            cover.run()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][:4], ["content", "update", "posts", cover.POST_ID])
        self.assertNotIn("--draft", calls[1])
        self.assertIn("--rev", calls[1])
        payload = __import__("json").loads(calls[1][calls[1].index("--data") + 1])
        self.assertEqual(list(payload), ["featured_image"])
        self.assertNotIn("dummy-secret", capture.getvalue())
        self.assertNotIn("dummy-jwt", capture.getvalue())


if __name__ == "__main__":
    unittest.main()
