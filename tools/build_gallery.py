# -*- coding: utf-8 -*-
"""投稿済みの絵を集めて、サイトのギャラリーを作り直す。

るぴちゃん指示（2026-08-31）＝
  「今後投稿済みの画像はここに全て見れるようにしておいてください。
    自動更新で、キャラ毎にSFWとNSFWを分けて」

拾う場所＝SNSレビューの `✅済み` の中で **実際に出したもの**だけ。
  ○ 投稿済み / 送信済み / 完了 を含む枝
  × 未使用 / 見送り / 振り分け直し前 / _旧 / _手の拡大

出すもの＝
  img/g/{sfw|nsfw}/{キャラ}/{id}.webp      （表示用・長辺1280）
  img/g/{sfw|nsfw}/{キャラ}/{id}_t.webp    （一覧用・長辺640）
  data/gallery.json                        （サイトが読む目録）

同じ絵は id（中身のhash）で見分けるので、**何度回しても増えない**。
消えた絵はJSONから外れ、webpも掃除する（--keep で残せる）。
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import unicodedata

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
IMG = os.path.join(SITE, "img", "g")
DATA = os.path.join(SITE, "data")

REVIEW = r"C:\Users\puram\OneDrive\Desktop\SNSレビュー"
SOURCES = [
    # (レビュー用フォルダ名, R18か)
    ("ひみつの眠り姫", False),
    ("ひみつの眠り姫R18", True),
]

# 出したものだけを拾う目印（パスのどこかに入っていること）
SHIPPED = ("投稿済み", "送信済み", "完了")
# 拾わない枝
SKIP = ("_旧", "手の拡大", "未使用", "見送り", "振り分け直し前", "定時にまわした")

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

MAX_FULL = 1280
MAX_THUMB = 640


def norm(s):
    return unicodedata.normalize("NFKC", s)


def who(folder, body):
    """キャラを決める。フォルダ名の末尾 → 本文の名乗り の順に見る。"""
    f = norm(folder)
    for key, words in ALIAS:
        for w in words:
            if re.search(r"[_\-\s]" + re.escape(w) + r"(_\d+)?$", f, re.I):
                return key
    # 本文の「〇〇です」で名乗っている場合
    head = (body or "")[:80]
    for key, words in ALIAS:
        for w in words:
            if w in head and not w.islower():
                return key
    # フォルダ名のどこかに1人だけ出てくるなら、それ
    hit = [k for k, ws in ALIAS if any(w in f for w in ws)]
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        return "three"
    return None


def read_post(folder):
    """投稿文.txt から 本文・投稿時間 を拾う。"""
    p = os.path.join(folder, "投稿文.txt")
    if not os.path.exists(p):
        return "", ""
    try:
        t = io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return "", ""
    m = re.search(r"-{3,}\s*本文 ここから\s*-{3,}(.*?)-{3,}\s*本文 ここまで", t, re.S)
    body = (m.group(1).strip() if m else "")
    d = re.search(r"【投稿時間】\s*(\d{4}-\d{2}-\d{2})", t)
    return body, (d.group(1) if d else "")


SNS = r"C:\ClaudeCode\aibs-ops\scripts\sns"
PLANS = os.path.join(SNS, "_plans")
PLANS_SITES = os.path.join(SNS, "_plans_sites")

# 🚨🔞ここが「どこまで載せるか」の線（るぴちゃん決定 2026-08-31）＝
#   「**Level1までに絞ってGitHubに置いて、それ以上はちちぷい/pixivへ導線だけ**」。
#   GitHubの利用規約は性的にわいせつな内容を禁じているので、Level2/3は**置かない**。
#   Levelが引けなかった絵も**載せない**（安全側に倒す）。
MAX_NSFW_LEVEL = 1

_scene_map = None
_level_map = None


def scene_map():
    """フォルダ名は長さで切られている。計画JSONの label→scene で元に戻す。"""
    global _scene_map
    if _scene_map is not None:
        return _scene_map
    _scene_map = {}
    for cur, _d, files in os.walk(PLANS):
        for f in files:
            if not f.endswith(".json"):
                continue
            try:
                doc = json.load(io.open(os.path.join(cur, f), encoding="utf-8"))
            except Exception:
                continue
            if isinstance(doc, list):                     # 形の違うJSONが混ざっている
                continue
            for p in doc.get("posts", []):
                if not isinstance(p, dict):
                    continue
                lab, sc = (p.get("label") or "").strip(), (p.get("scene") or "").strip()
                if lab and sc and lab != sc:
                    _scene_map[lab] = sc
    return _scene_map


def level_map():
    """枠の名前 → Level。定時は `label`／`scene`、イベントは `tag` で引ける。

    同じ名前に複数のLevelがぶら下がったら**高いほうを採る**（安全側）。
    """
    global _level_map
    if _level_map is not None:
        return _level_map
    _level_map = {}

    def put(key, lv):
        key = (key or "").strip()
        if not key or lv is None:
            return
        try:
            lv = int(lv)
        except (TypeError, ValueError):
            return
        _level_map[key] = max(_level_map.get(key, -1), lv)

    for root in (PLANS, PLANS_SITES):
        for cur, _d, files in os.walk(root):
            for f in files:
                if not f.endswith(".json"):
                    continue
                try:
                    doc = json.load(io.open(os.path.join(cur, f), encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(doc, dict):
                    continue
                for k in ("posts", "events"):
                    for e in (doc.get(k) or []):
                        if not isinstance(e, dict):
                            continue
                        lv = e.get("level")
                        for key in (e.get("label"), e.get("scene"), e.get("tag")):
                            put(key, lv)
    return _level_map


def level_of(title, folder):
    """その絵のLevel。分からなければ None。"""
    m = level_map()
    for key in (title, folder, re.sub(r"[_\-](lilia|sefi|tiru|リリア|セフィリア|ティルナ)(_\d+)?$",
                                      "", folder, flags=re.I)):
        if key and key.strip() in m:
            return m[key.strip()]
    return None


def caption(folder):
    """一覧に出す短い言葉。**フォルダ名の場面**だけから作る。

    🚨投稿文の本文は使わない（るぴちゃん指示 2026-08-31＝
      「投稿文のセリフは投稿時に変えていたりするので使わない」）。
    """
    f = re.sub(r"^\d+[_\-]\d{3,4}[_\-]", "", folder)      # 先頭の「3_2130_」
    f = re.sub(r"^(投稿|予約)?[#＃]?", lambda m: "#" if "#" in m.group(0) or "＃" in m.group(0) else "", f, count=1)
    while True:                                            # 「Threads_Bluesky_」
        n = re.sub(r"^(Threads|Bluesky|X|Discord)[_\-]", "", f)
        if n == f:
            break
        f = n
    f = re.sub(r"[_\-](lilia|sefi|tiru|リリア|セフィリア|ティルナ)(_\d+)?$", "", f, flags=re.I)
    f = re.sub(r"^\d{4}-\d{2}-\d{2}[_\-]", "", f)
    f = f.replace("_", " ").strip()
    full = scene_map().get(f)                              # 切られた名前を元に戻す
    if full:
        f = full
    return f[:60] or "無題"


def date_of(path, fallback):
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", path)
    return "-".join(m.groups()) if m else fallback


def sha_of(path):
    with io.open(path, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:12]


def known_levels():
    """前に出した目録に残っているLevel。

    🚨計画JSONは古いものが消える。そのとき Level が引けなくなって、
    　 **一度載せた絵が次のビルドで消えてしまう**。前回の判定を覚えておく。
    """
    p = os.path.join(DATA, "gallery.json")
    if not os.path.exists(p):
        return {}
    try:
        doc = json.load(io.open(p, encoding="utf-8"))
    except Exception:
        return {}
    return {e["id"]: e["level"] for e in doc.get("items", [])
            if isinstance(e, dict) and e.get("level") is not None}


def collect():
    out = []
    held = []                      # 🔞Level2以上＝サイトには置かず、外部への導線だけにする
    prev = known_levels()
    for folder_name, is_r18 in SOURCES:
        root = os.path.join(REVIEW, folder_name, "✅済み")
        if not os.path.isdir(root):
            print("[warn] 無い:", root)
            continue
        for cur, dirs, files in os.walk(root):
            rel = os.path.relpath(cur, root)
            if any(s in cur for s in SKIP):
                dirs[:] = []
                continue
            if not any(s in rel for s in SHIPPED):
                continue
            pics = sorted(f for f in files if f.lower().endswith(".png"))
            if not pics:
                continue
            base = os.path.basename(cur)
            body, day = read_post(cur)
            key = who(base, body)
            if key is None:
                print("[skip] キャラが分からない:", base)
                continue
            title = caption(base)
            lv = level_of(title, base) if is_r18 else None
            for i, f in enumerate(pics, 1):
                src = os.path.join(cur, f)
                this = lv
                if is_r18:
                    if this is None:                       # 計画JSONが消えていたら前回の判定
                        this = prev.get(sha_of(src))
                    # 🚨🔞Level2以上と、**分からないもの**はサイトに置かない
                    if this is None or this > MAX_NSFW_LEVEL:
                        held.append((base, "Level%s" % ("不明" if this is None else this), 1))
                        continue
                out.append(dict(
                    src=src, char=key, nsfw=is_r18, level=this,
                    title=title, date=date_of(cur, day), folder=base, no=i,
                ))
    if held:
        n = sum(x[2] for x in held)
        print("🔞サイトに置かなかった: %d枠 %d枚（Level%d超・または不明）"
              % (len(held), n, MAX_NSFW_LEVEL))
        for b, why, c in held[:10]:
            print("   ", why, b[:46], "(%d枚)" % c)
        if len(held) > 10:
            print("    ほか %d枠" % (len(held) - 10))
    return out, sum(x[2] for x in held)


def convert(item, force=False):
    """webpを作って、相対パスと寸法を返す。"""
    h = sha_of(item["src"])
    zone = "nsfw" if item["nsfw"] else "sfw"
    d = os.path.join(IMG, zone, item["char"])
    os.makedirs(d, exist_ok=True)
    full = os.path.join(d, h + ".webp")
    thumb = os.path.join(d, h + "_t.webp")
    im = None
    if force or not (os.path.exists(full) and os.path.exists(thumb)):
        im = Image.open(item["src"]).convert("RGB")
        for dst, cap, q in ((full, MAX_FULL, 82), (thumb, MAX_THUMB, 78)):
            c = im.copy()
            c.thumbnail((cap, cap), Image.LANCZOS)
            c.save(dst, "WEBP", quality=q, method=5)
    w, h_px = Image.open(full).size
    rp = "img/g/%s/%s/%s.webp" % (zone, item["char"], h)
    return h, rp, rp.replace(".webp", "_t.webp"), w, h_px


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="webpを作り直す")
    ap.add_argument("--keep", action="store_true", help="使わなくなったwebpを消さない")
    ap.add_argument("--dry", action="store_true", help="書かずに数える")
    a = ap.parse_args()

    items, held = collect()
    print("見つけた絵:", len(items), "枚")
    if a.dry:
        for it in items[:200]:
            print("  ", "🔞" if it["nsfw"] else "  ", it["char"], it["date"], it["title"][:34])
        return 0

    os.makedirs(DATA, exist_ok=True)
    seen, entries = set(), []
    for it in items:
        try:
            hid, full, thumb, w, h = convert(it, a.force)
        except Exception as e:                       # 壊れた1枚で全部を止めない
            print("[fail]", os.path.basename(it["src"]), e)
            continue
        if hid in seen:                              # 同じ絵が2箇所にあっても1つに
            continue
        seen.add(hid)
        entries.append(dict(id=hid, char=it["char"], nsfw=it["nsfw"],
                            level=it.get("level"),
                            title=it["title"], date=it["date"],
                            src=full, thumb=thumb, w=w, h=h))

    entries.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    counts = {}
    for e in entries:
        k = ("nsfw" if e["nsfw"] else "sfw") + ":" + e["char"]
        counts[k] = counts.get(k, 0) + 1

    doc = dict(
        updated=max([e["date"] for e in entries] or [""]),
        chars={k: v for k, v in CHARS.items()},
        counts=counts,
        max_nsfw_level=MAX_NSFW_LEVEL,
        held=held,                 # サイトに置かなかった枚数（外部への導線に添える）
        items=entries,
    )
    io.open(os.path.join(DATA, "gallery.json"), "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=1))

    # 目録から外れたwebpを片付ける
    if not a.keep:
        alive = set()
        for e in entries:
            alive.add(os.path.basename(e["src"]))
            alive.add(os.path.basename(e["thumb"]))
        gone = 0
        for cur, _dirs, files in os.walk(IMG):
            for f in files:
                if f.endswith(".webp") and f not in alive:
                    os.remove(os.path.join(cur, f))
                    gone += 1
        if gone:
            print("使わなくなったwebpを消した:", gone)

    for k in sorted(counts):
        print("  %-14s %d枚" % (k, counts[k]))
    print("目録:", os.path.join(DATA, "gallery.json"), "／ 合計", len(entries), "枚")
    return 0


if __name__ == "__main__":
    sys.exit(main())
