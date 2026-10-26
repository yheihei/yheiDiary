# Yheiの日記 — EmDash / Cloudflare

個人の日記と主要プロジェクトへの入口。EmDash 1.3.1、Astro SSR、Cloudflare Workers + D1 のテンプレートから作成。過去画像は既存の S3 / CloudFront から参照し、R2 に複製しない。

## ローカル確認

```sh
npm ci
npm run build
npm run typecheck
npx emdash seed --validate seed/seed.json
```

公開候補の `import-ready-posts.xml` と監査資料は `../private/migration/` にある。この private ディレクトリを Git や公開 asset に入れない。

## 公開に必要な残作業

1. R2 は本人が有効化済み。既存 Wrangler から `r2 bucket list` の読み取りが成功し、現在バケット0件。本人希望の月額 $5 上限を守る具体策・課金条件を確認してから新規リソースを作る。
2. 初回管理者を守る。推奨候補は [EmDash 公式 Cloudflare Access 認証](https://docs.emdashcms.com/guides/authentication/#cloudflare-access)。Worker の `/_emdash/*` 全体（API 含む）を本人だけに許す Access application/policy、teamDomain、`CF_ACCESS_AUDIENCE` を設定する。これは新規 security 設定なので、本人の具体的な承認前に作成しない。Access を本番で使う場合、passkey は排他で不要となり、最初の Access 認証ユーザーが Admin になる。Access が未設定なら保護なしで公開しない。
3. R2 の費用条件と Access 保護が承認・確認できてから、こちらで公式テンプレートの Worker・D1・R2 リソースを作成し `npm run deploy`。本人が Access で最初にログインして Admin になる（passkey の手入力は不要）。別方式の passkey を選ぶ場合は本人による登録が必要。
4. `../private/migration/import-ready-posts.xml` を posts に公式 WXR import する。ローカル D1 では実際に901件すべて published と検証済み。Cloudflare 側でも件数、本文、画像、内部リンク、日本語表示を再確認する。Copy media は行わない。
5. 初回インポート後は `../private/migration/RECOVERY.md` の通り D1 Time Travel bookmark と DB backup を保存する。旧 WordPress と CloudFront は維持する。

Google Analytics は ID が未提示なので設定していない。旧ドメイン依存画像の詳細は非公開監査表を参照。

補足: インポート用 WXR は公開投稿901件に加え、アイキャッチ参照用の最小添付 metadata 100件を持つ。EmDash 公式 parser で141件のアイキャッチ参照がすべて解決することを確認済み。メディアコピー工程は省略する。

## 緊急休止

公開後に同じ Worker を 503 の最小応答へ差し替え、通常版へ戻すコマンドを準備した。`npm run site:pause` / `npm run site:resume`。本番デプロイはまだ実施していない。経路、Version URL、費用の制限事項と dry run は [`maintenance/README.md`](maintenance/README.md) を参照。
