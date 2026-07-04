---
name: kindle-ocr
description: Kindle for Mac の本をフォーカスを奪わずにバックグラウンドで全ページキャプチャし、macOS Vision framework でローカル OCR して ~/kindle-library/<書名>/ に book.md と index.md を生成、その内容について会話できるようにする。「Kindleの本を取り込みたい」「本をOCRしてClaudeと話したい」「〜（取り込み済みの本）について教えて」等の依頼時に使用。
---

# Kindle 書籍のキャプチャ → ローカル OCR → 会話

Kindle for Mac で開いた本を、ユーザーが Mac を使い続けたまま裏で全ページスクショし、
ローカル OCR でテキスト化して会話用の `book.md` / `index.md` を作るパイプライン。

## 前提（初回のみ確認）

1. **権限**: Claude Code を動かしているターミナルアプリに
   - システム設定 → プライバシーとセキュリティ → **画面収録**
   - 同 → **アクセシビリティ**（`AXIsProcessTrusted` で確認可能）
2. **venv**: `python3 -m venv .venv && .venv/bin/pip install pyobjc-framework-Quartz pyobjc-framework-Vision`
3. **本の選択は自動化できない**: ユーザーに Kindle アプリで対象の本を開いてもらう
   （**背面で OK、最小化と Space 移動だけ不可**）。書名の検出と保存先の決定は自動

## 取り込み手順

```bash
# 0. 本の向きを判定: 横書き本 → --key right / 縦書き・漫画 → --key left
#    見開き表示にしておくと1スクショで2ページ分撮れて効率的

# 1. 動作確認（撮影→1ページ送り→撮影→差分チェック）
.venv/bin/python capture.py --test --key right

# 2. 先頭まで巻き戻し
.venv/bin/python capture.py --rewind --key right

# 3. 全ページキャプチャ。書名を柱から自動検出し
#    ~/kindle-library/<書名スラッグ>/pages/ に保存（バックグラウンド実行推奨、~350ページで6分程度）
.venv/bin/python capture.py --key right --interval 1.5

# 4. ローカル OCR → book.md（本文・見出し付き）+ index.md（見出し索引）
.venv/bin/python ocr.py --book ~/kindle-library/<書名スラッグ>
```

キャプチャ中はユーザーに「Kindle ウィンドウの上にマウスを載せないで」と伝える
（ツールバーが写り込むため）。

## 会話フェーズ（コンテキスト節約の作法）

`book.md` は10万トークン級なので**丸ごと読まない**。必ず2段階で:

1. `index.md` を読む（数KB。見出し → `page_NNNN.png` の対応表）
2. 該当範囲だけを切り出して読む:
   `sed -n '/<!-- page_0042.png -->/,/<!-- page_0050.png -->/p' book.md`
3. index に載っていない語を探すときは `grep -n` で book.md を検索し、
   ヒット位置の前後のマーカー範囲だけ読む。同義語（例: 監視/モニタリング/
   オブザーバビリティ）で複数回引くこと

## 仕組み（トラブルシュート用）

- ページ送り: `CGEventPostToPid` で Kindle プロセスに直接キーイベント。**フォーカス不要**
- スクショ: `screencapture -l <windowID>` は背面に隠れたウィンドウも撮れる
- 終端検知: 同一画面を検知したら待ち時間を伸ばしつつキー再送を3回試し、
  それでも変化しなければ最終ページと判断（UI 写り込みや描画遅延での誤検知対策）
- OCR: 認識行を x 座標で左右ページに分離し上→下で結合。y 座標でウィンドウUI・柱・
  ノンブルを除外（本文帯は y 0.06〜0.90）。行高さが本文中央値の1.35倍超なら見出し化
- 書名検出: 柱（y≥0.90、タイトルバーの "Kindle" は除外）の最長行。
  ダーシが「→」に誤認識されるためスラッグ化時に区切り文字として処理済み

## 注意・制約

- **OCR は必ずローカル（ocr.py）で行う。Claude やサブエージェントに書籍画像の
  全文文字起こしをさせてはいけない**（著作権保護された市販書籍の複製にあたるため
  一貫して辞退される。ローカル OCR なら私的複製の範囲で完結する）
- 生成データ（pages/, book.md, index.md）は個人利用限定。共有・再配布・コミット不可。
  データは意図的にリポジトリ外（~/kindle-library/）に置いており、.gitignore でも保険をかけている
- 会話フェーズ: `book.md` はユーザーが用意したドキュメントとして扱い、
  要約・解説・該当箇所の短い引用で答える
- 途中で止まったら: `--rewind` → 再キャプチャが最も確実
