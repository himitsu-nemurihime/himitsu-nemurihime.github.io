# -*- coding: utf-8 -*-
"""ギャラリーを作り直して、変わっていたらコミット（＋push）する。

るぴちゃん指示（2026-08-31）＝「投稿済みの画像は自動更新でサイトに出す」。
定時バッチから毎日これを呼ぶ。中身が変わっていない日は何もしない。

  python tools/update_site.py           # 作り直してコミットまで
  python tools/update_site.py --push    # push もする（バッチはこっち）
  python tools/update_site.py --dry     # 数えるだけ
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)


def run(args, **kw):
    return subprocess.run(args, cwd=SITE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    build = [sys.executable, os.path.join(HERE, "build_gallery.py")]
    if a.dry:
        build.append("--dry")
    r = run(build)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        print("[NG] ギャラリーの作り直しに失敗した")
        return 1
    if a.dry:
        return 0

    if run(["git", "status", "--porcelain"]).stdout.strip() == "":
        print("[skip] 変わっていないので、そのまま")
        return 0

    n = len([x for x in run(["git", "status", "--porcelain"]).stdout.splitlines() if x.strip()])
    run(["git", "add", "-A"])
    msg = "ギャラリーを更新（%d件の差分）\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>" % n
    r = run(["git", "commit", "-m", msg])
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        print("[NG] コミットに失敗した")
        return 1
    print("コミットした:", run(["git", "log", "--oneline", "-1"]).stdout.strip())

    if a.push:
        r = run(["git", "push", "origin", "main"])
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            print("[NG] push に失敗した")
            return 1
        print("push した → https://himitsu-nemurihime.github.io/")
    else:
        print("（push はしていない。--push で送る）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
