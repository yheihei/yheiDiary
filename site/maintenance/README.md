# 日記サイトの緊急休止と再開

このフォルダは **`yhei-diary-emdash` だけ**の公開 Worker を一時休止させるための運用手順です。2026-10-25 19:55 JST 現在、Cloudflare の Worker は休止版です。AWS、旧 WordPress、他 Worker には触れません。

初回公開の前提: 本人限定 Access と費用通知は設定済みです。DB migration と記事投入、本番の公開経路監査が必要です。通常版と休止版の `workers_dev`、routes、`preview_urls` は一致しないとスクリプトが停止します。現設定は `workers.dev` のみ有効、Version URL は `preview_urls: false` です。将来 custom domain や route を加える際は、両方の設定を更新してから dry run を実施してください。

```sh
cd /Users/yhei/emdash/diary/site
npm run site:maintenance:test
npm run site:pause:dry-run
npm run site:resume:dry-run

# 公開後、緊急休止
npm run site:pause
# 復旧確認後の再開
npm run site:resume
```

休止コマンドは対象アカウントと Worker 名を固定し、既存デプロイの読み取り確認に成功した場合だけ、同じ Worker に依存なしの 503 ページをデプロイします。未作成なら停止し、休止版 Worker を新設しません。全パスで `Cache-Control: no-store`、`Retry-After: 60`、`noindex` を返します。休止版には Astro/EmDash の import、D1/R2/KV/Images/Assets の binding、cron、Queue consumer がありません。通常版の毎分 cron は `crons: []` で明示的に解除します。進行中だった cron を受けても休止コードの `scheduled` は何もしません。再開コマンドは Astro を再ビルドし、**生成された** `dist/server/wrangler.json` から同じ Worker をデプロイします。Remote D1 の ID と R2 バケットが設定・作成されていなければ本番デプロイは成立しません。D1/R2 は削除しません。`--strict` によりリモート変更との競合時には失敗します。

デプロイ後は実際の `workers.dev` URL と全 custom route で `/`、記事、`/_emdash/*`、静的 asset path の応答を確認してください。休止時はすべて 503、再開時は通常表示へ戻ることを確認します。アクセス制御が先に応答する管理画面は、本人認証後に確認します。古いキャッシュや外部 CDN に既に保存されたファイルはこの Worker の差替えだけで消去できません。

**停止の成立条件:** 旧 Worker の Version URL と preview/deployment URL が無効または本人限定であること、R2 の `r2.dev` / custom bucket public URL が無いこと、同じ R2/D1 へ到達する他 Worker や Queue consumer が無いことを公開前と休止時に点検します。Version URL は旧版の binding を使えるため、通常 hostname の差替えだけでは止まりません。現ローカル設定には Queue consumer はありません。将来追加する場合は休止手順を再設計します。

休止中も Worker への要求、保存済みの R2/D1 データ、既存契約などの費用が必ずゼロになるとは保証しません。費用アラートは hard cap ではありません。課金を確実に遮断する機能として本手順を扱わず、Cloudflare 利用状況を確認してください。Workers Paid への加入は行いません。

公式根拠: [Wrangler 設定と `crons: []`](https://developers.cloudflare.com/workers/wrangler/configuration/)、[Version URL の無効化](https://developers.cloudflare.com/workers/versions-and-deployments/version-urls/)、[workers.dev と他公開経路](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)。
