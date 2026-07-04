#!/usr/bin/env python3
"""キャプチャ画像を macOS 内蔵の Vision framework でローカル OCR して Markdown 化する。

- 完全ローカル処理（ネットワーク・API 不使用）
- 見開き2ページを想定: 認識結果を x 座標で左右ページに分け、上→下の順に結合
- 画面上端（アプリのヘッダー/書名）と下端（ページ番号）は座標で除外
- 行の高さ（フォントサイズ相当）から見出しを推定し Markdown 見出しにする
- book.md と同時に、見出し→見開き番号の索引 index.md を生成

使い方:
  python ocr.py --book ~/kindle-library/本のスラッグ    # book/pages/*.png → book/book.md, book/index.md
  python ocr.py --book <dir> --limit 2                  # 動作確認用
"""

import argparse
import re
import statistics
import sys
from pathlib import Path

import Quartz
import Vision

# 正規化座標 (0=下端, 1=上端)。この範囲の外はアプリUI・柱・ノンブルとみなして本文から除外
# 柱（書名ヘッダー）は y≈0.92、ウィンドウタイトルバーは y≈0.98、本文上端は y≈0.87 付近
CONTENT_TOP = 0.90
CONTENT_BOTTOM = 0.06

# 本文行の高さ中央値に対してこの倍率を超える行を見出しとみなす
HEADING_RATIO = 1.35


def recognize(path: Path):
    """1枚の画像を OCR して [(x, y, height, text)] を返す。座標は正規化済み・行中心。"""
    url = Quartz.CFURLCreateWithFileSystemPath(
        None, str(path), Quartz.kCFURLPOSIXPathStyle, False
    )
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["ja-JP", "en-US"])
    request.setUsesLanguageCorrection_(True)
    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"OCR failed: {err}")
    lines = []
    for obs in request.results() or []:
        cand = obs.topCandidates_(1)
        if not cand.count():
            continue
        text = cand.objectAtIndex_(0).string()
        bb = obs.boundingBox()  # 原点は左下
        x = bb.origin.x + bb.size.width / 2
        y = bb.origin.y + bb.size.height / 2
        lines.append((x, y, bb.size.height, text))
    return lines


IGNORE_CHROME = {"kindle", "amazon kindle"}


def book_title(image_path: Path) -> str:
    """ページ上端の柱（書名ヘッダー）から書名を取る。見つからなければ空文字。

    ウィンドウタイトルバーの "Kindle" 表記は除外する。
    """
    tops = [t for x, y, h, t in recognize(image_path)
            if y >= CONTENT_TOP and t.strip().lower() not in IGNORE_CHROME]
    if not tops:
        return ""
    return max(tops, key=len).strip()


def slugify(title: str) -> str:
    """書名を保存ディレクトリ名に変換。サブタイトルは切り落とし、パスに使えない文字を除く。"""
    # 「→」はダーシ（——）の OCR 誤認識として頻出するため区切り扱いにする
    for sep in ("——", "――", "─", "—", "―", "→", "〜", "~", ":", "：", "|"):
        title = title.split(sep)[0]
    title = re.sub(r'[/\\<>*?"\']+', "", title).strip()
    title = re.sub(r"\s+", "-", title)
    return title[:40] or "untitled"


def spread_to_text(lines):
    """見開きの認識行を 左ページ上→下、右ページ上→下 の順に結合。大きい行は見出しに。"""
    body = [l for l in lines if CONTENT_BOTTOM < l[1] < CONTENT_TOP]
    if not body:
        return ""
    median_h = statistics.median(h for _, _, h, _ in body)
    left = sorted([l for l in body if l[0] < 0.5], key=lambda l: -l[1])
    right = sorted([l for l in body if l[0] >= 0.5], key=lambda l: -l[1])
    out = []
    for _, _, h, text in left + right:
        if h > median_h * HEADING_RATIO and len(text) >= 2:
            out.append(f"\n## {text}\n")
        else:
            out.append(text)
    return "\n".join(out)


def looks_like_heading(text: str) -> bool:
    """行高さ判定をすり抜けた本文（文の断片）を索引から弾く。"""
    if len(text) > 30:
        return False
    if "。" in text or "、" in text:
        return False
    return True


def build_index(book_md: Path, index_md: Path):
    """book.md の見出しと見開きマーカーから索引を作る。"""
    current = "?"
    entries = []
    for line in book_md.read_text().splitlines():
        m = re.match(r"<!-- (page_\d+\.png) -->", line)
        if m:
            current = m.group(1)
            continue
        if line.startswith("## ") and looks_like_heading(line[3:].strip()):
            entries.append(f"- {line[3:].strip()} — `{current}`")
    index_md.write_text(
        "# 索引（見出し → 見開き画像番号）\n\n"
        "質問に答えるときは、まずこの索引で該当範囲を特定し、\n"
        "book.md の該当 `<!-- page_NNNN.png -->` マーカー間だけを読むこと。\n\n"
        + "\n".join(entries)
        + "\n"
    )
    return len(entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True,
                    help="本のディレクトリ（中に pages/ があること）")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    book_dir = Path(args.book).expanduser()
    files = sorted((book_dir / "pages").glob("page_*.png"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        sys.exit(f"{book_dir}/pages に画像が見つからない")

    out = book_dir / "book.md"
    with out.open("w") as f:
        title = book_title(files[0]) or book_title(files[min(2, len(files) - 1)])
        if title:
            f.write(f"# {title}\n")
        for i, p in enumerate(files, 1):
            text = spread_to_text(recognize(p))
            f.write(f"\n<!-- {p.name} -->\n\n{text}\n")
            print(f"\r{i}/{len(files)} {p.name}", end="", flush=True)
    n = build_index(out, book_dir / "index.md")
    print(f"\n完了: {out} ({out.stat().st_size:,} bytes), index.md 見出し {n} 件")


if __name__ == "__main__":
    main()
