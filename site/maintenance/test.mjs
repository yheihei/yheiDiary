import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

const forbiddenEnv = new Proxy({}, {
  get(_target, key) { throw new Error(`Maintenance accessed binding ${String(key)}`); },
});

test("all public and admin paths return a non-cacheable 503 without bindings", async () => {
  for (const path of ["/", "/posts/blog-entry-4", "/_emdash/admin", "/_emdash/api/posts", "/_astro/sample.css"]) {
    const response = await worker.fetch(new Request(`https://example.workers.dev${path}`), forbiddenEnv);
    assert.equal(response.status, 503);
    assert.match(response.headers.get("cache-control"), /no-store/);
    assert.match(await response.text(), /一時休止中/);
  }
  const head = await worker.fetch(new Request("https://example.workers.dev/", { method: "HEAD" }), forbiddenEnv);
  assert.equal(head.status, 503);
  assert.equal(await head.text(), "");
  worker.scheduled({}, forbiddenEnv);
});
