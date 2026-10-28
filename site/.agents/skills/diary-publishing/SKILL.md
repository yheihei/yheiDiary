---
name: diary-publishing
description: 日記サイト yhei.dev に、ローカルの日記原稿を投稿する。原稿を読み、Gemini でアイキャッチを3枚作って1枚選び、S3 に置き、アイキャッチ付きの下書きを作って確かめ、公開日を原稿の日付の21:00にして公開し、本番を確かめて URL と画像を報告する。「この日記投稿しといて」「原稿置いたから上げて」「アイキャッチ作って投稿して」のように原稿のパスや日記の題名を渡されたとき、公開済みの日記にアイキャッチを付けるとき、公開済みの日記を直すときに使う。サイトのデザインやコードの変更は building-emdash-site、EmDash CLI そのものの使い方は emdash-cli を見る。
---

# yhei.dev の日記投稿

原稿のパスを1つ渡されたら、下の1〜7を順に最後まで回す。依頼で原稿を名指しされたことを、その1本の公開OKとみなす。ほかの原稿は公開しない。

スクリプトは `site/.agents/skills/diary-publishing/scripts/` にあり、どれもリポジトリの直下 `/Users/yhei/emdash/diary` で実行する。どのスクリプトも、結果がはっきりしないときは「停止:」と出して止まる。止まったら同じ操作をやり直さず、管理画面か `content get` で今の状態を読んでから考える。

記事ごとの記録は `private/drafts/<slug>.source.json` に集まる。記事 ID、公開日、アイキャッチの URL などを、スクリプトが読み書きする。

スクリプトを直したら `python3 site/.agents/skills/diary-publishing/scripts/test_scripts.py` を回す。本番には触れないテストで、秘密を出さないことも見ている。

## 1. 原稿を読む

```bash
python3 site/.agents/skills/diary-publishing/scripts/prepare_post.py "/Users/yhei/Documents/yhei/diary/20261027 - 脆弱性祭り.md" --name vulnerability-fest
```

- 原稿のファイル名は `YYYYMMDD - タイトル.md`。日付が slug の頭と公開日になり、残りが題名になる。
- `--name` は題名を短い英語にした slug の後半。小文字とハイフンだけ。slug は `20261027-vulnerability-fest` のようになる。
- 原稿そのものは変えない。本文の JSON を `private/drafts/<slug>.post.json` に、写しを `<slug>.source.md` に置く。
- 原稿は自分でも全部読む。アイキャッチの絵を考えるのに要る。
- 本文の画像は、原稿にある S3 の URL をそのまま使う。公開 URL のない画像があるとスクリプトは止まるので、本人に聞く。
- X のポストの URL だけの行は、そのまま残す。記事ページのスクリプトが X のカードに変える。oEmbed の HTML を埋め込む必要はない。

## 2. アイキャッチを3枚作って1枚選ぶ

1. [references/eyecatch.md](references/eyecatch.md) を読み、絵柄の決まりに沿って、構図の違うプロンプトを3つ書く。置き場所は `private/drafts/<slug>/eyecatch/a.prompt.md`、`b.prompt.md`、`c.prompt.md`。
2. 3枚をまとめて作る。Gemini の Nano Banana 2 で 16:9 の 1K、1枚あたり約0.07ドル。

   ```bash
   python3 site/.agents/skills/diary-publishing/scripts/make_eyecatch.py <slug>
   ```

   生成は edit-youtube-video スキルの `thumbnail.mjs` が受け持ち、Gemini の API キーもそちらが自分で読む。キーの入った `.env` は開かない。
3. 3枚とも Read で実際に見て、1枚選ぶ。見るところは references/eyecatch.md の「選び方」。読める文字や実在のロゴが混ざっていたら、その案は使わない。3枚ともだめなら、プロンプトを直して作り直す。
4. 選んだ理由とほかの2枚との違いを、短く報告に書く。

## 3. S3 に置く

```bash
python3 site/.agents/skills/diary-publishing/scripts/upload_eyecatch.py <slug> private/drafts/<slug>/eyecatch/a-1.jpg --alt "絵の中身を短く書いた代替テキスト"
```

- 本人がいつも画像を置いている公開バケット `yhei-obsidian-images` の `diary/featured/<slug>-<sha256の先頭16字>.jpg` に置く。名前が中身で決まるので、同じ画像を2回上げても増えない。
- AWS の認証は本人の aws CLI の設定をそのまま使う。設定ファイルや Obsidian のプラグイン設定は開かない。
- 置いたあと、ログインなしの取得で HTTP 200 と中身の一致まで確かめる。取れなければ止まる。バケットの公開設定は変えない。
- Claude Code の権限の判定が公開の場所へのアップロードとして止めることがある。そのときは回り道をせず、本人に「上げてよいか」を聞くか、このコマンドを本人の Terminal で打ってもらう。
- アイキャッチは `provider: "external"` の外部 URL で記事に付く。サイトは外部ドメインの画像を加工せずそのまま `<img>` と og:image に出す。EmDash のメディアライブラリには上げない。`/_emdash/api/media/file/` は Cloudflare Access の内側にあり、未ログインの読者には見えない。

## 4. 下書きを作って確かめる

```bash
python3 site/.agents/skills/diary-publishing/scripts/create_draft.py <slug>
```

- 同じ slug か題名の記事が既にあれば作らずに止まる。
- 3で置いたアイキャッチを付けて、`content create posts --draft` を1回だけ実行する。アイキャッチがまだないと止まる。どうしても付けずに作るときだけ `--without-eyecatch` を付ける。
- できたら記事 ID を読み直して確かめる。`emdash content get posts <ID> --raw` で状態が draft、題名、本文、`featured_image.src` が S3 の URL であること。公開 URL `https://yhei.dev/posts/<slug>` が 404 であること。CLI を直接叩くときの認証は下の「認証」を見る。食い違いがあれば公開せずに本人に聞く。

## 5. 公開する

```bash
python3 site/.agents/skills/diary-publishing/scripts/publish_post.py <slug>
```

- 公開日を原稿のファイル名の日付の 21:00 JST にする。先に下書きへ公開日を入れ、それから `content publish` を1回実行する。EmDash は入っている公開日を保ったまま公開する。
- 公開日の書き換えは公式 CLI に引数がないので、`published_at.mjs` が管理画面の「Publication date」と同じ PUT を、サイトに入っている EmDash の公式クライアントで送る。
- 公開後に読み直し、状態 published、公開日、題名、本文、アイキャッチが下書きと同じことを確かめる。

## 6. 本番を確かめる

```bash
node site/.agents/skills/diary-publishing/scripts/check_live.mjs <slug> --out private/drafts/published-<公開した日のYYYYMMDD>/<slug>
```

- ログインなしで、Playwright の WebKit を使い、iPhone 375×812 の3倍ダークと PC 1280 幅ライトで記事の先頭を撮る。日記一覧とトップのカードも撮る。
- 確かめること: 記事ページが HTTP 200、題名、日付、アイキャッチが読み込めていること、og:image が S3 の URL でログインなしに取れること、X のカードの数、横にはみ出していないこと、日記一覧とトップに載っていてサムネイルが出ていること。
- 結果は `checks.json` に残る。スクリプトが「ok」でも、撮った画像は Read で自分の目で見る。
- Playwright は `~/.cache/yhei-diary-checker` に置いてある。ないときはスクリプトの先頭に書いた2行で入れる。

## 7. 報告する

本人への報告は、記事の URL、アイキャッチの画像、選んだ理由を1〜2文、本番で確かめたこと、撮った画像のパス。アイキャッチと記事の先頭の画像は SendUserFile で送る。止まったところがあれば、どこで止まり、本人に何をしてほしいかを書く。

## 公開済みの記事を直す

- アイキャッチを付けるか差し替えるときは、2と3のあとに次を実行する。公開状態と公開日を保ったまま `featured_image` だけを送る。差し替えのときは `--replace` を付ける。

  ```bash
  python3 site/.agents/skills/diary-publishing/scripts/attach_eyecatch.py <slug>
  ```

- 本文を直すときは、`content get --raw --published` で `_rev` を取り、`content update --rev <_rev> --draft` で下書きにしてから確かめて公開する。新しく作り直さない。revision の衝突で止まったら、読み直してから考える。
- どれも、終わったら6で本番を確かめる。

## 認証

- サイトの管理 API は Cloudflare Access の内側にある。本人の `cloudflared` のログインを使い、Access のトークンを `EMDASH_HEADERS` の `Cf-Access-Token` として子プロセスにだけ渡す。トークンの期限が切れていたら、スクリプトは EmDash に送る前に止まる。そのときは `cloudflared access login https://yhei.dev/_emdash/admin` を出力を捨てて1回実行し、本人にブラウザでログインしてもらう。
- EmDash の PAT は、本人がリポジトリ直下の `.env` に `EMDASH_PAT` として書いている。`.env` は git に入らず、権限は 0600。読むのはスクリプトだけで、`.env` を開く、表示する、写すことはしない。PAT とトークンを argv、ログ、ファイルに出さない。PAT の権限は `content:read`、`content:write`、`schema:read` で足りる。
- 管理者権限の `emdash login`、サービストークンの作成、Access の設定変更はしない。本番の DB を SQL で触らない。`npm run deploy` は本人が打つ。日記の投稿に deploy は要らない。

## 止まったときの見分け方

- Cloudflare Access のログイン画面への 302 は、トークンの期限切れか、Access の内側の URL を未ログインで開いている。
- Cloudflare の Error 1010 はクライアントの拒否。Python の urllib で起きる。curl と node の fetch は通る。
- KV の 429 は日ごとの上限、Workers の 1102 は CPU の上限。どれも自動でやり直さず、ユーザーエージェントの偽装や上限の変更もしない。記事は今の状態のまま残し、どこで止まったかを本人に書く。
