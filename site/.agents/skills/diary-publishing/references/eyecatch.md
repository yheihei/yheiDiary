# アイキャッチの絵柄とプロンプト

## これまでのアイキャッチ

| 記事 | 絵柄 | 画像 |
| --- | --- | --- |
| WordPressをEmDashへ移行 | 暗い紺と紫に琥珀色の、落ち着いた editorial 調 | `https://yhei.dev/featured/wordpress-to-emdash-67cb0a1a78b4fb9e.jpg` |
| AI slopがとんでもない | クリーム色の紙に色鉛筆とガッシュ、絵本のような暖かい調子 | `https://yhei.dev/featured/ai-slop-7dfe45517a94cc86.jpg` |
| 脆弱性祭り | AI slop と同じ色鉛筆調 | `https://yhei-obsidian-images.s3.ap-northeast-1.amazonaws.com/diary/featured/20261027-vulnerability-fest-57a08d11e0122f22.jpg` |
| ITエンジニアは不要になるか | 色鉛筆調。承認のハンコを押し続けるエンジニアとロボットたち | `https://yhei-obsidian-images.s3.ap-northeast-1.amazonaws.com/diary/featured/20261028-it-engineers-obsolete-7d11da2ec3854b72.jpg` |

日記の語り口に合うのは色鉛筆調なので、これを基本にする。後ろ姿でぼさぼさ頭のエンジニアと三毛猫が続けて出ているので、話に合うなら入れる。トップと日記一覧ではカードが並ぶので、小さく縮めても何の絵か分かる構図にする。

## 3案の分け方

- A と B は色鉛筆調で、構図を変える。たとえば A は本人の机まわりの近景、B は話の比喩を大きく描いた遠景。
- C は editorial 調にして、絵柄そのものを比べられるようにする。
- どの案も、記事でいちばん言いたいことか、いちばん面白い比喩を1つだけ絵にする。要素を詰め込まない。

## プロンプトの型

英語で書く。最後の2段落は毎回そのまま入れる。

```text
Create a finished editorial illustration for a Japanese personal diary post about <記事の中身を1文で>.

Style: hand-drawn colored pencil and gouache on warm cream paper, like a cozy humorous picture-book illustration. Visible pencil strokes, soft muted colors: warm cream, teal, rust orange, mustard, muted navy.

Scene: <何がどこにあるか。人物は後ろ姿か小さく。画面の文字は描かせない>.

Mood: <wry, curious などを2〜3語>. Strong composition that reads at thumbnail size.

No text, letters, numbers, logos, brand marks, company names, identifiable people, watermarks, or readable screen content. 16:9 landscape image.
```

C の Style の段落は次に差し替える。

```text
Style: elegant dark charcoal, deep indigo, muted violet, and warm amber accents. Tactile paper texture mixed with clean modern geometry, like a calm tech editorial cover.
```

実在の会社や製品の名前は、プロンプトにも書かない。記事が特定の会社の話でも、「大きなビル」「遠くの塔」のように置き換える。

## 選び方

1. 拡大して、読める文字、数字、ロゴ、実在のブランドに見えるものがないか見る。あればその案は落とす。
2. 400px ぐらいに縮めても、何の絵か分かるか。
3. 記事を読んだ人が「ああ、あの話」と思えるか。
4. これまでのアイキャッチと並べて浮かないか。

## 代替テキスト

絵に描いてあることを1文で書く。記事の要約や感想は書かない。例: 「窓の外で雷を落とす神々の雲をよそに、机でアップデートを続けるエンジニアと机の下の猫」。

## 脆弱性祭りで作った3案

`private/design-candidates-2026-10-28/` にプロンプトと画像がある。

- A を採用。色鉛筆調で、窓の外の雲が怒った神々の顔になって雷を落とし、手前でエンジニアがアップデートを続けている。机の下に三毛猫。「神々の怒り」と「アプデせよ」が一目で分かる。
- B は同じ色鉛筆調で、雷に打たれるビルを笑う通行人と、屋上で黙々と直すエンジニア。「笑うな」の話は出せたが、要素が多く、縮めると何の絵か分かりにくい。
- C は editorial 調で、光るドームに守られた机と雷の落ちる塔。整っているが、日記の可笑しみが出ない。
