import { decodeSlug } from "emdash";

/**
 * Slugs to try when looking up an entry or term from a route parameter.
 *
 * Entries imported from WordPress keep its slug format: non-ASCII characters
 * stay percent-encoded with lowercase hex ("perfume%e3%81%a8..."). decodeSlug
 * turns the URL into "perfumeと老い", which matches native EmDash slugs but not
 * those imported ones, so the WordPress form is tried as well.
 */
export function slugCandidates(raw: string | undefined): string[] {
	const slug = decodeSlug(raw);
	if (!slug) return [];

	const wordpressSlug = encodeURIComponent(slug).replace(/%[0-9A-F]{2}/g, (hex) =>
		hex.toLowerCase(),
	);
	return wordpressSlug === slug ? [slug] : [slug, wordpressSlug];
}
