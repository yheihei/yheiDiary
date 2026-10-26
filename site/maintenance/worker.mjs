// Minimal emergency response. Do not import Astro, EmDash, or a storage client.
const page = `<!doctype html>
<html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>一時休止中 | Yheiの日記</title>
<style>body{font-family:system-ui,sans-serif;margin:0;background:#f6f5f1;color:#242424;min-height:100vh;display:grid;place-items:center}main{max-width:36rem;padding:2rem;line-height:1.8}h1{font-size:clamp(1.6rem,6vw,2.3rem);line-height:1.3}</style>
<main><h1>ただいま一時休止中です</h1><p>日記サイトの公開を一時停止しています。再開までお待ちください。</p></main></html>`;
const headers = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store, max-age=0",
  "Retry-After": "60",
  "X-Robots-Tag": "noindex, nofollow, noarchive",
  "X-Content-Type-Options": "nosniff",
};
export default {
  fetch(request) {
    return new Response(request.method === "HEAD" ? null : page, { status: 503, headers });
  },
  // A trigger already in flight during deployment also performs no storage work.
  scheduled() {},
};
