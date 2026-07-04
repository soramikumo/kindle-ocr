#!/usr/bin/env python3
"""Kindle for Mac のページを、フォーカスを奪わずにバックグラウンドでキャプチャする。

仕組み:
- スクショ: `screencapture -l <windowID>` — 背面に隠れたウィンドウでも撮れる
- ページ送り: CGEventPostToPid で Kindle プロセスに直接キーイベントを送る
  （System Events と違い、最前面である必要がない）

制約:
- Kindle ウィンドウは最小化しない・現在の Space に置いておく（背面は OK）
- ターミナル（実行元プロセス）に「画面収録」と「アクセシビリティ」の権限が必要

保存先は最初のスクショから書名を OCR して ~/kindle-library/<書名>/pages/ に自動決定する。

使い方:
  python capture.py --test              # 1ページだけ送って動作確認
  python capture.py --key left          # 縦書き本（右→左に進む）: 左矢印で次ページ
  python capture.py --key right         # 横書き本: 右矢印で次ページ
"""

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import Quartz

from ocr import book_title, slugify

KEY_CODES = {"left": 123, "right": 124}


def find_kindle_window():
    """Kindle のメインウィンドウ (windowID, pid, title) を返す。"""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID
    )
    candidates = []
    for w in windows:
        owner = w.get(Quartz.kCGWindowOwnerName, "")
        if "kindle" not in owner.lower():
            continue
        if w.get(Quartz.kCGWindowLayer, 1) != 0:
            continue
        bounds = w.get(Quartz.kCGWindowBounds, {})
        area = bounds.get("Width", 0) * bounds.get("Height", 0)
        if area < 100 * 100:
            continue
        candidates.append((area, w))
    if not candidates:
        return None
    # 一番大きいウィンドウをメインとみなす
    _, w = max(candidates, key=lambda t: t[0])
    return (
        w[Quartz.kCGWindowNumber],
        w[Quartz.kCGWindowOwnerPID],
        w.get(Quartz.kCGWindowName, "") or "(no title)",
    )


def screenshot(window_id: int, path: Path) -> bool:
    """指定ウィンドウを影なしで撮影。成功したら True。"""
    r = subprocess.run(
        ["screencapture", "-x", "-o", "-l", str(window_id), str(path)],
        capture_output=True,
    )
    return r.returncode == 0 and path.exists() and path.stat().st_size > 0


def send_key(pid: int, key_code: int):
    """フォーカスを奪わず、対象プロセスに直接キーを送る。"""
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, key_code, down)
        Quartz.CGEventPostToPid(pid, ev)
        time.sleep(0.05)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="~/kindle-library",
                    help="ライブラリのルート。<library>/<書名スラッグ>/pages/ に保存される")
    ap.add_argument("--out", default=None,
                    help="保存先を直接指定（指定時は書名の自動検出をしない）")
    ap.add_argument("--key", choices=["left", "right"], default="left",
                    help="次ページのキー（縦書き=left, 横書き=right）")
    ap.add_argument("--interval", type=float, default=1.5,
                    help="ページ送り後の待ち秒数")
    ap.add_argument("--max", type=int, default=1500, help="最大ページ数")
    ap.add_argument("--test", action="store_true",
                    help="動作確認: 撮影→1ページ送り→撮影 だけ行う")
    ap.add_argument("--rewind", action="store_true",
                    help="キャプチャせず、逆方向キーを送って本の先頭まで戻る")
    args = ap.parse_args()

    found = find_kindle_window()
    if not found:
        sys.exit("Kindle のウィンドウが見つからない。アプリを起動して本を開いて、"
                 "最小化せずに置いておいて（背面でOK）")
    window_id, pid, title = found
    print(f"対象: window={window_id} pid={pid} title={title!r}")

    if args.out:
        out = Path(args.out).expanduser()
    else:
        # 1枚試し撮りして柱の書名から保存先を決める
        probe = Path("/tmp/_kindle_probe.png")
        if not screenshot(window_id, probe):
            sys.exit("スクショ失敗。ターミナルに「画面収録」権限があるか確認して")
        title = book_title(probe)
        probe.unlink(missing_ok=True)
        slug = slugify(title) if title else "untitled"
        out = Path(args.library).expanduser() / slug / "pages"
        print(f"書名検出: {title!r} → 保存先 {out}")
    out.mkdir(parents=True, exist_ok=True)
    key_code = KEY_CODES[args.key]

    if args.rewind:
        # 進行方向と逆のキーを、画面が変わらなくなるまで送る
        back_code = KEY_CODES["left" if args.key == "right" else "right"]
        tmp = out / "_rewind.png"
        prev = None
        same = 0
        for i in range(args.max):
            send_key(pid, back_code)
            time.sleep(max(args.interval * 0.5, 0.6))
            screenshot(window_id, tmp)
            h = md5(tmp)
            same = same + 1 if h == prev else 0
            prev = h
            if same >= 3:
                print(f"先頭到達 ({i+1}回)")
                break
        else:
            print(f"--max ({args.max}) 回送っても先頭に着かず")
        tmp.unlink(missing_ok=True)
        return

    if args.test:
        a, b = out / "_test_before.png", out / "_test_after.png"
        if not screenshot(window_id, a):
            sys.exit("スクショ失敗。ターミナルに「画面収録」権限があるか確認して")
        send_key(pid, key_code)
        time.sleep(max(args.interval, 1.0))
        screenshot(window_id, b)
        same = md5(a) == md5(b)
        print(f"before/after 同一: {same}")
        if same:
            print("→ キーが届いていない可能性。アクセシビリティ権限を確認するか、"
                  "本が最終ページ/表紙でないか確認して")
        else:
            print("→ バックグラウンドでのページ送り成功！本番実行できる")
        return

    prev_hash = None
    i = 0
    for _ in range(args.max):
        i += 1
        path = out / f"page_{i:04d}.png"
        if not screenshot(window_id, path):
            sys.exit(f"page {i}: スクショ失敗（権限 or ウィンドウ消失）")
        h = md5(path)
        if h == prev_hash:
            # ページが進んでいない。誤検知（UI表示・描画遅延・イベント取りこぼし）
            # の可能性があるので、間隔を伸ばしてキー再送を3回まで試す
            recovered = False
            for retry in range(1, 4):
                print(f"\rpage {i:04d}: 変化なし、リトライ {retry}/3", end="", flush=True)
                send_key(pid, key_code)
                time.sleep(args.interval + 2.0 * retry)
                screenshot(window_id, path)
                h = md5(path)
                if h != prev_hash:
                    recovered = True
                    break
            if not recovered:
                path.unlink()
                print(f"\n最終ページ検出。{i-1} ページ保存した")
                break
        prev_hash = h
        print(f"\rpage {i:04d} 保存            ", end="", flush=True)
        send_key(pid, key_code)
        time.sleep(args.interval)
    else:
        print(f"\n--max ({args.max}) に到達して終了")


if __name__ == "__main__":
    main()
