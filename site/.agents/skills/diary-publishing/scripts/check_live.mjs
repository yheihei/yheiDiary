// Usage: node check_live.mjs <slug> --out <dir relative to the repository root>
// Checks one published diary post on production without logging in, the way a
// reader sees it, and takes screenshots with Playwright WebKit:
//   article page  HTTP 200, title, date, eyecatch loaded, og:image, X cards, no sideways scroll
//   /posts and /  the post is listed and its eyecatch thumbnail loaded
//   og:image      fetchable anonymously as an image
// Expected values come from private/drafts/<slug>.source.json. Writes checks.json
// and PNGs to --out, prints a summary, and exits 1 when anything is off.
//
// Playwright lives outside the repository. First time only:
//   npm install --prefix ~/.cache/yhei-diary-checker playwright@1.56.1
//   npx --prefix ~/.cache/yhei-diary-checker playwright install webkit
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL("../../../../..", import.meta.url)));
const SITE = "https://yhei.dev";
const PLAYWRIGHT =
	process.env.YHEI_DIARY_PLAYWRIGHT ??
	join(homedir(), ".cache/yhei-diary-checker/node_modules/playwright/index.mjs");
const X_URL_ONLY =
	/>\s*https?:\/\/(?:www\.|mobile\.)?(?:twitter|x)\.com\/\w+\/status(?:es)?\/\d+\S*?\s*</g;

const [slug, flag, outArg] = process.argv.slice(2);
if (!slug || flag !== "--out" || !outArg) {
	console.error("usage: node check_live.mjs <slug> --out <dir>");
	process.exit(2);
}
if (!existsSync(PLAYWRIGHT)) {
	console.error(`Playwright がありません: ${PLAYWRIGHT}\nファイル先頭の2行で入れてください。`);
	process.exit(2);
}
const source = JSON.parse(readFileSync(join(ROOT, "private/drafts", `${slug}.source.json`), "utf8"));
const eyecatch = source.eyecatch?.featuredImage?.src ?? null;
const out = resolve(ROOT, outArg);
mkdirSync(out, { recursive: true });
const { webkit, devices } = await import(PLAYWRIGHT);

const sameInstant = (a, b) => Boolean(a && b) && new Date(a).getTime() === new Date(b).getTime();
const failures = [];
const expect = (ok, what) => {
	if (!ok) failures.push(what);
	return ok;
};

const browser = await webkit.launch();
const contexts = {
	iphone: await browser.newContext({
		userAgent: devices["iPhone 13 Mini"].userAgent,
		viewport: { width: 375, height: 812 },
		screen: { width: 375, height: 812 },
		deviceScaleFactor: 3,
		isMobile: true,
		hasTouch: true,
		colorScheme: "dark",
		locale: "ja-JP",
	}),
	pc: await browser.newContext({
		viewport: { width: 1280, height: 900 },
		deviceScaleFactor: 2,
		colorScheme: "light",
		locale: "ja-JP",
	}),
};

async function checkArticle(name, context) {
	const url = `${SITE}/posts/${slug}`;
	const html = await (await fetch(url)).text();
	const xExpected =
		(html.match(X_URL_ONLY) ?? []).length + (html.match(/<blockquote class="twitter-tweet"/g) ?? []).length;
	const page = await context.newPage();
	const response = await page.goto(url, { waitUntil: "load" });
	if (xExpected) {
		await page
			.waitForFunction(
				(n) => [...document.querySelectorAll("[data-post-content] iframe[id^='twitter-widget']")]
					.filter((f) => f.getBoundingClientRect().height > 150).length >= n,
				xExpected,
				{ timeout: 45000, polling: 500 },
			)
			.catch(() => {});
	}
	await page.evaluate(() => window.scrollTo(0, 0));
	await page.waitForTimeout(800);
	const state = await page.evaluate(() => {
		const hero = document.querySelector(".post-hero__media img");
		return {
			title: document.querySelector("h1")?.textContent?.trim(),
			datetime: document.querySelector("time[datetime]")?.getAttribute("datetime"),
			dateText: document.querySelector("time[datetime]")?.textContent?.trim(),
			ogImage: document.querySelector('meta[property="og:image"]')?.content ?? null,
			hero: hero && { loaded: hero.complete && hero.naturalWidth > 0, src: hero.currentSrc || hero.src },
			xCards: document.querySelectorAll("[data-post-content] iframe[id^='twitter-widget']").length,
			scrollWidth: document.documentElement.scrollWidth,
			viewportWidth: window.innerWidth,
		};
	});
	const file = `${slug}-${name}-top.png`;
	await page.screenshot({ path: join(out, file) });
	await page.close();
	expect(response?.status() === 200, `${name}: 記事ページが HTTP ${response?.status()}`);
	expect(state.title === source.title, `${name}: 題名が違う (${state.title})`);
	expect(sameInstant(state.datetime, source.publishedAt), `${name}: 日付が違う (${state.datetime})`);
	expect(state.scrollWidth <= state.viewportWidth, `${name}: 横にはみ出している`);
	expect(state.xCards >= xExpected, `${name}: X のカードが ${state.xCards}/${xExpected}`);
	if (eyecatch) {
		expect(state.hero?.loaded && state.hero.src === eyecatch, `${name}: アイキャッチが出ていない`);
		expect(state.ogImage === eyecatch, `${name}: og:image が違う (${state.ogImage})`);
	}
	return { url, status: response?.status(), xExpected, ...state, files: [file] };
}

async function checkListing(name, context, path, cardSelector) {
	const page = await context.newPage();
	const response = await page.goto(SITE + path, { waitUntil: "load" });
	const state = await page.evaluate(
		({ href, cardSelector }) => {
			const hrefs = [...document.querySelectorAll('a[href^="/posts/"]')]
				.map((a) => a.getAttribute("href"))
				.filter((h, i, all) => /^\/posts\/[^/?#]+$/.test(h) && all.indexOf(h) === i);
			const card = document.querySelector(`a[href="${href}"]`)?.closest(cardSelector);
			card?.setAttribute("data-check-card", "");
			return { position: hrefs.indexOf(href) + 1 };
		},
		{ href: `/posts/${slug}`, cardSelector },
	);
	const file = `${slug}-${name}.png`;
	const card = page.locator("[data-check-card]");
	if (await card.count()) {
		// Thumbnails load lazily; bring the card into view before reading them.
		await card.scrollIntoViewIfNeeded();
		await card.locator("img").first().evaluate((img) => img.decode?.().catch(() => {})).catch(() => {});
		await page.waitForTimeout(600);
		state.image = await card.evaluate((el) => {
			const img = el.querySelector("img");
			return img && { loaded: img.complete && img.naturalWidth > 0, src: img.currentSrc || img.src };
		});
		await card.screenshot({ path: join(out, file) });
	}
	await page.close();
	expect(response?.status() === 200, `${name}: HTTP ${response?.status()}`);
	expect(state.position > 0, `${name}: 記事が載っていない`);
	if (eyecatch) expect(state.image?.loaded && state.image.src === eyecatch, `${name}: サムネイルが出ていない`);
	return { url: SITE + path, status: response?.status(), ...state, files: [file] };
}

const result = { checkedAt: new Date().toISOString(), webkitVersion: browser.version(), slug, pages: {} };
try {
	result.pages.articleIphone = await checkArticle("iphone", contexts.iphone);
	result.pages.articlePc = await checkArticle("pc", contexts.pc);
	result.pages.list = await checkListing("list-iphone", contexts.iphone, "/posts", "article.post");
	result.pages.top = await checkListing("top-iphone", contexts.iphone, "/", "li");
	if (eyecatch) {
		const r = await fetch(eyecatch);
		result.ogImage = { url: eyecatch, status: r.status, type: r.headers.get("content-type") };
		expect(r.status === 200 && r.headers.get("content-type")?.startsWith("image/"), "og:image を未ログインで取得できない");
	}
} finally {
	await browser.close();
}
result.failures = failures;
writeFileSync(join(out, "checks.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify({ ok: failures.length === 0, failures, out }, null, 2));
process.exit(failures.length ? 1 : 0);
