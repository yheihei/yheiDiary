---
name: diary-publishing
description: Turn a local Markdown diary manuscript into an EmDash draft for this yhei.dev site, verify it, and publish only when the owner explicitly asks for that specific article.
---

# Diary publishing for yhei.dev

Use this for a new local diary manuscript or a requested revision of an existing diary entry. This skill is site-local to `/Users/yhei/emdash/diary`; it does not authorize publication by itself. For EmDash command syntax, read `../emdash-cli/SKILL.md` and check the installed CLI's `--help` before changing production content.

## Prepare the manuscript

1. Read the specified Markdown and any images it directly references. Do not modify the original. Determine its intended title, slug, and publication date from the manuscript or the owner's instruction; do not confuse a date in the filename/frontmatter with body text. Preserve existing S3/CloudFront image URLs and record unresolved links instead of inventing replacements or copying media to R2.
2. Prepare `{ "title": "...", "content": "..." }` as UTF-8 JSON under `private/drafts/` with mode `0600`. Keep source metadata in a separate private sidecar if needed. Inspect Markdown formatting, embeds, image links, and the resulting editor preview. The 2026-10-25 example uses `private/drafts/20261025-wordpress-to-emdash.post.json`; its fixed helper `site/scripts/post_diary_draft.py` is for that one manuscript only.
3. Choose a slug deliberately. Check the public route and EmDash content list/get for the same slug, title, or existing ID. A failed request is not proof of absence. If a prior create result is uncertain, inspect the site before considering another create.

## Create and check a draft

- Prefer the official EmDash CLI for content operations. The CLI's `content create` publishes by default; always specify `--draft` for a new draft. The local generic helper [scripts/create_draft.py](scripts/create_draft.py) fixes the target to `https://yhei.dev`, takes a prepared private JSON path and slug, checks all listed titles/slugs, and invokes official `emdash content create posts --draft` once. It prints only the new item ID. It stops without retry on errors or uncertain results.
- The site's admin API is protected by Cloudflare Access. Use the owner's existing `cloudflared` login. The official EmDash CLI accepts `EMDASH_HEADERS`; pass the cached Access JWT transiently as `Cf-Access-Token`. Use an owner-entered EmDash PAT with only `content:read`, `content:write`, `schema:read`. The owner chose a 90-day PAT for the initial workflow; request authorization for any new grant or changed scope/expiry. Since 2026-10-28 the owner keeps the PAT as `EMDASH_PAT` in the gitignored `.env` at the repository root, mode `0600`, and writes it there themselves. The helper reads it from there, falls back to hidden Terminal input when it is empty, and passes both credentials only to child-process environment, never argv, logs, or Git. Never open, print, or copy `.env`; the helper is the only reader. Do not inspect the PAT generation screen after the owner generates it, nor read clipboard/Terminal history. Do not run admin-scoped `emdash login`, create service tokens, or loosen Access.
- Example after the owner has approved the scoped credential and draft creation: `cd /Users/yhei/emdash/diary && python3 site/.agents/skills/diary-publishing/scripts/create_draft.py private/drafts/new-post.json new-post-slug`. Do not put the PAT in that command.
- Verify the returned ID in the admin editor: draft status, title, body against the prepared JSON, image URLs and actual image display, and unauthenticated public URL not served. If content does not match, stop and resolve the discrepancy with the owner.

## Revise or publish

- For an existing entry, identify its ID and use the official CLI's `content get` revision token before `content update --draft`; stop on revision conflict. Do not use create for a revision. An API token with `content:write` may also allow deletion or publication, so use only the operation the owner requested.
- Ask for specific authorization before publishing an article. The approval for the 2026-10-25 example does not authorize later articles. Immediately before publication, re-read the same ID and verify its draft/title/body. Publish through the existing protected admin UI or an authorized official CLI operation; never recreate the item. Then verify admin status is published and the actual URL returns HTTP 200 with the expected title, body, and original image URL. If the publish result is uncertain, read the current status before doing anything else.
- Distinguish failures: Cloudflare Access redirects/authorization, Cloudflare Error 1010 client rejection, KV 429 quota, and Workers CPU 1102 require different diagnosis. Avoid automated retries, user-agent impersonation, quota/plan changes, or security bypass. Preserve the post and report the exact stopping point.
