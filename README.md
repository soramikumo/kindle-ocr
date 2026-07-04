# kindle-ocr

自分が購入した Kindle 書籍を、Kindle for Mac の画面キャプチャ + **完全ローカルの OCR**
（macOS Vision framework）でテキスト化し、Claude Code と「本について会話する」ための
個人用ツール / スキルです。

## 特徴

- **フォーカスを奪わない**: `CGEventPostToPid` で Kindle プロセスに直接キーイベントを
  送るため、キャプチャ中も Mac を普通に使い続けられる（Kindle は背面のままで OK）
- **完全ローカル OCR**: テキスト化は macOS 内蔵の Vision framework で行う。
  書籍の内容がネットワークや外部 API に送られることはない
- **書名の自動整理**: ページ上部の柱から書名を検出し、`~/kindle-library/<書名>/` に
  `pages/`（画像）、`book.md`（本文テキスト）、`index.md`（見出し索引）を自動生成
- **コンテキスト節約**: 会話時は `index.md` で該当範囲を特定してから `book.md` の
  必要な部分だけを読む2段階検索

## セットアップ

```bash
python3 -m venv .venv
.venv/bin/pip install pyobjc-framework-Quartz pyobjc-framework-Vision
```

macOS の権限（システム設定 → プライバシーとセキュリティ）:

- **画面収録**: 実行するターミナルアプリに付与
- **アクセシビリティ**: 同上

## 使い方

Kindle for Mac で本を開いた状態で（背面で OK、最小化と Space 移動は不可）:

```bash
# 1. 動作確認（横書き本は --key right、縦書き・漫画は --key left）
.venv/bin/python capture.py --test --key right

# 2. 先頭ページまで巻き戻し
.venv/bin/python capture.py --rewind --key right

# 3. 全ページキャプチャ（書名を自動検出して ~/kindle-library/<書名>/pages/ に保存）
.venv/bin/python capture.py --key right

# 4. ローカル OCR → book.md / index.md 生成
.venv/bin/python ocr.py --book ~/kindle-library/<書名>
```

あとは Claude Code で `book.md` のある場所を参照しながら質問するだけです。

## 必ず読んでください（利用上の注意）

このツールは**私的利用の複製**（著作権法30条が定める範囲）を想定して作られています。
以下を理解したうえで、各自の責任で使用してください。

- **生成したデータ（`pages/`、`book.md`、`index.md`）の共有・再配布・アップロード・
  公開リポジトリへのコミットは絶対にしないでください。** 私的複製の範囲を超え、
  著作権侵害（複製権・公衆送信権の侵害）になります
- このツールは DRM の解除・復号を行いません（画面に表示されたものを OS 標準機能で
  撮影しているだけです）。ただし、**Amazon の利用規約に抵触する可能性は否定できず、
  アカウント停止等のリスクは利用者自身が負います**
- 私的複製の解釈には議論の余地があり、また法律は変わります。ここに書かれた内容は
  **法的助言ではありません**。判断に迷う場合は使用しないでください
- 本ツールに、複数書籍の一括処理・データの共有や出力の外部送信といった機能を
  追加する予定はありません。その方向の要望・PR は受け付けません（設計思想です）
- デフォルトの `.gitignore` は書籍データの誤コミットを防ぐためのものです。
  外さないでください

## 仕組み

| 段階 | 使用技術 | 備考 |
|---|---|---|
| ページ送り | `CGEventPostToPid` (Quartz) | フォーカス不要でキーイベントを直接送信 |
| 撮影 | `screencapture -l <windowID>` | 背面ウィンドウも撮影可 |
| 終端検知 | 画像ハッシュ比較 + リトライ | UI 写り込み・描画遅延での誤検知対策済み |
| OCR | Vision framework (`VNRecognizeTextRequest`) | ja-JP / en-US、完全ローカル |
| 構造化 | 行高さによる見出し推定 | book.md に `##`、index.md に索引を生成 |

## ライセンス

コードは MIT License。ただし上記「利用上の注意」の遵守を強く求めます。
