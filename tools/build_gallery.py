# -*- coding: utf-8 -*-
"""投稿済みの絵を集めて、このサイトのギャラリーを作り直す。

るぴちゃん指示（2026-08-31）＝
  「今後投稿済みの画像はここに全て見れるようにしておいてください。
    自動更新で、キャラ毎にSFWとNSFWを分けて」

🚨2026-09-02＝**中身は共通エンジンに移した**（`aibs-ops/scripts/sns/gallery_core.py`）。
　 ルピナスのサイトにも同じ作りのギャラリーを足すことになったため、
　 **同じロジックを2本持たない**ようにした。ここはこのサイトの設定だけを持つ。

  python tools/build_gallery.py [--force] [--keep] [--dry]
"""
import argparse
import os
import sys

sys.path.insert(0, r"C:\ClaudeCode\aibs-ops\scripts\sns")
import gallery_core as G                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# 🚨🔞ここが「どこまで載せるか」の線（るぴちゃん決定 2026-08-31）＝
#   「**Level1までに絞ってGitHubに置いて、それ以上はちちぷい/pixivへ導線だけ**」。
#   GitHubの利用規約は性的にわいせつな内容を禁じているので、Level2/3は**置かない**。
#   Levelが引けなかった絵も**載せない**（安全側に倒す）。
MAX_NSFW_LEVEL = 1

CHARS = {
    "lilia": dict(name="リリア・ノワール", short="リリア", color="#C9D3E8"),
    "sefi": dict(name="セフィリア・プリムヴェール・アジュール", short="セフィリア", color="#E8C87E"),
    "tiru": dict(name="ティルナ・フルーレット", short="ティルナ", color="#8FC7A8"),
    "three": dict(name="三人いっしょ", short="三人", color="#C9A7E8"),
}
# フォルダ名の末尾やタイトルに出てくる呼び名
ALIAS = [
    ("lilia", ("lilia", "リリア")),
    ("sefi", ("sefi", "セフィリア", "セフィ")),
    ("tiru", ("tiru", "ティルナ", "ティル")),
]

SITE = G.Site(
    site_dir=os.path.dirname(HERE),
    sources=[("ひみつの眠り姫", False), ("ひみつの眠り姫R18", True)],
    chars=CHARS,
    alias=ALIAS,
    img_rel="img/g",
    data_name="gallery.json",
    max_nsfw_level=MAX_NSFW_LEVEL,
    # 🚨この3人の計画だけを見る。指定しないと**AIBS三姉妹の同時刻の枠**を
    #   拾ってしまい、Level やキャラを取り違える。
    plans_dirs={"lilia", "lilia_r18", "sefi", "sefi_r18", "tiru", "tiru_r18"},
    # ギャラリーのJSは正本から配ってもらう（ルピナスのサイトと同じものが入る）
    js_dest="assets/gallery.js",
)


BASE_URL = "https://himitsu-nemurihime.github.io/"


def write_sitemap():
    """🔎2026-10-28（TASKS 0-446・Search Console）＝一番上の html のうち noindex でない物だけを載せる
    （prompts/ は全部 noindex＝載せない・google*.html は所有権の確認ファイル）"""
    import datetime
    import glob
    import io
    root = SITE.site_dir
    urls = []
    for f in sorted(glob.glob(os.path.join(root, "*.html"))):
        name = os.path.basename(f)
        if name.startswith("google"):
            continue
        if "noindex" in io.open(f, encoding="utf-8", errors="replace").read(20000):
            continue
        day = datetime.date.fromtimestamp(os.path.getmtime(f)).isoformat()
        loc = BASE_URL if name == "index.html" else BASE_URL + name
        urls.append(f"<url><loc>{loc}</loc><lastmod>{day}</lastmod></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + "".join(urls) + "</urlset>\n")
    p = os.path.join(root, "sitemap.xml")
    old = io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    if old != xml:
        io.open(p, "w", encoding="utf-8", newline="\n").write(xml)
    return len(urls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="webpを作り直す")
    ap.add_argument("--keep", action="store_true", help="使わなくなったwebpを消さない")
    ap.add_argument("--dry", action="store_true", help="書かずに数える")
    a = ap.parse_args()
    rc = G.build(SITE, force=a.force, keep=a.keep, dry=a.dry)
    if not a.dry:
        print("sitemap.xml:", write_sitemap(), "ページ")
    return rc


if __name__ == "__main__":
    sys.exit(main())
