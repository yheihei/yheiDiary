// Usage: node published_at.mjs <collection> <id> <rev> <publishedAt>
// Sends the same request the admin's "Publication date" dialog sends:
// PUT /_emdash/api/content/<collection>/<id> with { _rev, publishedAt }.
// The official CLI has no flag for the publication date. This uses the site's
// installed EmDash client, so CSRF, Bearer and the EMDASH_HEADERS headers are
// added exactly as the CLI adds them. The token and headers come only from the
// environment and are never printed. Prints one JSON object.
const client = new URL("../../../../node_modules/emdash/dist/client/", import.meta.url);
const { EmDashClient } = await import(new URL("index.mjs", client));
const { customHeadersInterceptor, resolveCustomHeaders } = await import(new URL("cf-access.mjs", client));

const [collection, id, rev, publishedAt] = process.argv.slice(2);
const token = process.env.EMDASH_TOKEN;
if (!collection || !id || !rev || !publishedAt || !token) {
	console.log(JSON.stringify({ error: { message: "missing arguments or token" } }));
	process.exit(2);
}

const emdash = new EmDashClient({
	baseUrl: "https://yhei.dev",
	token,
	interceptors: [customHeadersInterceptor(resolveCustomHeaders())],
});

try {
	const data = await emdash.request(
		"PUT",
		`/content/${encodeURIComponent(collection)}/${encodeURIComponent(id)}`,
		{ _rev: rev, publishedAt },
	);
	console.log(JSON.stringify({ ok: true, item: data?.item ?? data }));
} catch (error) {
	console.log(JSON.stringify({
		error: { name: error?.name, code: error?.code, status: error?.status, message: error?.message },
	}));
	process.exit(1);
}
