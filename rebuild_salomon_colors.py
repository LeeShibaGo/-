# -*- coding: utf-8 -*-
"""Salomon 壞掉的多色卡:依官網重建顏色(預設只預覽,不寫入;APPLY=1 才寫)
------------------------------------------------------------
問題:舊的多色卡(p_salomon_1784396678297_*,共 183 張)每個顏色都用同一張圖、同一份庫存
(同步靠圖片對官網,圖片相同就全對到同一個官網商品)。官網是「一個顏色 = 一個商品頁」。
做法(老闆選方案 1):
  1. 每個舊顏色(中文名)對到官網同名商品的某個顏色(用「站上已經有獨立單色卡」的中英對照學翻譯)。
  2. 對得到、而且站上沒有獨立卡的顏色 -> 留在這張卡,改用官網自己的圖/尺寸/庫存。
  3. 站上已經有獨立單色卡的顏色 -> 從合併卡拿掉(每個顏色只出現一次)。
  4. 留不下任何顏色的卡 -> 標 hidden(不刪)。
  5. 對不到官網的舊顏色 -> 列在報告裡,套用時丟掉(資料本來就是錯的)。
"""
import json, os, re, sys, time, urllib.request
from collections import defaultdict

from sync_stock import load_products, merge_and_save, fix_size_key

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
APPLY = os.environ.get("APPLY") == "1"


def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            print("retry", url, e); time.sleep(5 * (i + 1))
    raise RuntimeError(url)


def norm(t):
    return re.sub(r"^(男款|女款)\s*", "", re.sub(r"^【NEW】", "", t or "")).strip().upper()


def en_colour(p):
    return (p["options"][0]["values"][0] if p.get("options") else "").strip()


def main():
    allp = []
    for page in range(1, 12):
        ps = get(f"https://salomon.jp/products.json?limit=250&page={page}").get("products", [])
        allp += ps
        if len(ps) < 250:
            break
        time.sleep(1.5)
    print("official products", len(allp))
    by_handle = {p["handle"]: p for p in allp}
    by_title = defaultdict(list)
    for p in allp:
        by_title[norm(p["title"])].append(p)

    cards = [p for p in load_products() if p.get("brand") == "Salomon"]
    handle_of = lambda c: (c.get("link") or "").rsplit("/", 1)[-1]
    bad = [c for c in cards if len(c.get("colors", [])) > 1 and
           len({(x.get("image") or "").split("?")[0] for x in c["colors"]}) == 1]
    bad_ids = {c["id"] for c in bad}
    standalone_handles = {handle_of(c) for c in cards if c["id"] not in bad_ids}

    # 英文 -> {中文...} 字典:從站上的獨立單色卡(官網商品已知)學出來
    tr = defaultdict(set)
    for c in cards:
        if c["id"] in bad_ids or len(c.get("colors", [])) != 1:
            continue
        p = by_handle.get(handle_of(c))
        if not p:
            continue
        en = [w.strip() for w in en_colour(p).split("/")]
        zh = [w.strip() for w in c["colors"][0]["name"].split("|")]
        if len(en) == len(zh):
            for e, z in zip(en, zh):
                tr[e].add(z)

    all_zh = set().union(*tr.values()) if tr else set()

    def word_ok(e, z):
        return z == e or z in tr.get(e, ())

    def score(zh_name, p):
        """None = 有詞明確衝突(不是同一個商品);否則回傳「有證據吻合的詞數」。
        字典裡沒有這個英文詞的翻譯(unknown)不算衝突也不算證據。"""
        zh = [w.strip() for w in zh_name.split("|")]
        en = [w.strip() for w in en_colour(p).split("/")]
        if len(zh) != len(en):
            return None
        ev = 0
        for e, z in zip(en, zh):
            if word_ok(e, z):
                ev += 1
            elif z.isascii() or z in all_zh:
                return None  # 舊名稱這個詞是別的英文詞的翻譯(或是不同的英文)=> 不是同一個顏色
            # 否則舊名稱用了字典沒見過的中文寫法(例如 杏仁奶油 vs 杏仁奶油色),不當衝突
        return ev if ev >= max(1, len(en) - 1) else None

    def best_match(zh_name, cands, used):
        sc = [(score(zh_name, p), p) for p in cands if p["handle"] not in used]
        sc = [(s_, p) for s_, p in sc if s_ is not None]
        if not sc:
            return None, 0
        top = max(s_ for s_, _ in sc)
        tops = [p for s_, p in sc if s_ == top]
        return (tops[0] if len(tops) == 1 else None), (len(tops) if len(tops) > 1 else 0)

    rows, changed, near_miss = [], [], []
    tot = dict(cards=0, old=0, kept=0, dup_removed=0, unmatched=0, hidden=0, ambiguous=0)
    for c in bad:
        gender = "w" if c["name"].startswith("女款") else ("m" if c["name"].startswith("男款") else None)
        cand = by_title.get(norm(c["name"]), [])
        if gender == "w":
            cand = [p for p in cand if "ウィメンズ" in (p.get("tags") or [])]
        elif gender == "m":
            cand = [p for p in cand if "ウィメンズ" not in (p.get("tags") or [])]
        kept, dups, unmatched, amb, used = [], [], [], 0, set()
        for old in c["colors"]:
            p, namb = best_match(old["name"], cand, used)
            if namb:
                amb += 1
            if p is None:
                unmatched.append(old["name"])
                near_miss.append((c["name"], old["name"], f"同標題官網商品 {len(cand)} 個"))
                continue
            used.add(p["handle"])
            if p["handle"] in standalone_handles and p["handle"] != handle_of(c):
                dups.append(old["name"])
                continue
            sizes, stock = [], {}
            for v in p["variants"]:
                s = fix_size_key((v.get("option2") or v.get("option1") or "").strip())
                if not s or s in stock:
                    continue
                sizes.append(s)
                stock[s] = 5 if v.get("available") else 0
            img = (p.get("images") or [{}])[0].get("src") or old.get("image")
            kept.append({"name": old["name"], "image": img, "sizes": sizes, "stock": stock,
                         "handle": p["handle"], "price": p["variants"][0].get("price")})
        tot["cards"] += 1; tot["old"] += len(c["colors"]); tot["kept"] += len(kept)
        tot["dup_removed"] += len(dups); tot["unmatched"] += len(unmatched); tot["ambiguous"] += amb
        hide = not kept
        tot["hidden"] += hide
        rows.append((c["id"], c["name"], len(c["colors"]), len(kept), len(dups), len(unmatched), amb, hide))
        if APPLY:
            if kept:
                c["colors"] = [{k: v for k, v in k_.items() if k not in ("handle", "price")} for k_ in kept]
                c["image"] = kept[0]["image"]
                c["link"] = "https://salomon.jp/products/" + kept[0]["handle"]
                try:
                    c["jpy"] = int(float(kept[0]["price"]))
                except (TypeError, ValueError):
                    pass
            else:
                c["hidden"] = True
            changed.append(c)

    print("ID\tNAME\tOLD\tKEPT\tDUP_REMOVED\tUNMATCHED\tAMBIG\tHIDE")
    for r in rows:
        print("\t".join(str(x) for x in r))
    print("TOTAL", tot)
    print("UNMATCHED_COUNT", len(near_miss))
    for nm in near_miss[:60]:
        print("UNM", nm)
    # 官網現在還有幾個同標題商品、官網整體商品數
    if APPLY and changed:
        merge_and_save(changed)
        print("已寫入", len(changed), "張卡")
    elif not APPLY:
        print("(預覽模式,沒有寫入任何資料)")


if __name__ == "__main__":
    main()
