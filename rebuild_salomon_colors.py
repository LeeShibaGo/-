# -*- coding: utf-8 -*-
"""Salomon 壞掉的多色卡:依官網重建顏色(預設只預覽,不寫入;APPLY=1 才寫)
------------------------------------------------------------
問題:舊的多色卡(p_salomon_1784396678297_*,共 183 張)每個顏色都用同一張圖、同一份庫存
(同步靠圖片對官網,圖片相同就全對到同一個官網商品)。官網是「一個顏色 = 一個商品頁」。
做法(老闆選方案 1):
  1. 每個舊顏色(中文名)對到官網同名商品的某個顏色(用「站上已經有獨立單色卡」的中英對照學翻譯)。
  2. 對得到、而且站上沒有獨立卡的顏色 -> 留在這張卡,改用官網自己的圖/尺寸/庫存。
  3. 站上已經有獨立單色卡的顏色 -> 從合併卡拿掉(每個顏色只出現一次)。
  4. 官網還在賣的東西不能隱藏:整張卡只剩重複色時把重複色放回來。
  5. 對不到官網的舊顏色:客人買過的保留並標缺貨(庫存 0),其餘丟掉。
  6. 只有「全部官網已下架、也沒有客人買過」的卡才標 hidden(不刪)。
"""
import json, os, re, sys, time, urllib.request
from collections import defaultdict

from firebase_admin import db
from sync_stock import firebase_app, load_products, merge_and_save, fix_size_key

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
    # 客人買過的 (商品ID, 顏色):就算官網下架也要留著,庫存標 0(缺貨)
    firebase_app()
    raw = db.reference("daigou-orders-v1").get() or {}
    orders = list(raw.values()) if isinstance(raw, dict) else [o for o in raw if o]
    ordered = set()
    for o in orders:
        for it in (o.get("items") or []):
            if it.get("productId") and it.get("color"):
                ordered.add((it["productId"], it["color"]))
    print("訂單數", len(orders), "買過的(商品,顏色)組合", len(ordered))
    handle_of = lambda c: (c.get("link") or "").rsplit("/", 1)[-1]
    bad = [c for c in cards if len(c.get("colors", [])) > 1 and
           len({(x.get("image") or "").split("?")[0] for x in c["colors"]}) == 1]
    bad_ids = {c["id"] for c in bad}
    standalone_handles = {handle_of(c) for c in cards if c["id"] not in bad_ids}

    # 英文 -> {中文...} 字典。站上獨立單色卡的顏色名稱是「未翻譯的英文」,學不到翻譯,
    # 所以改從舊合併卡學:每張舊卡的第一個顏色就是它的 link 對到的官網商品(逐詞對齊),
    # 再用「唯一對得上」的顏色反覆學新詞,直到不再增加。
    tr = defaultdict(set)

    def learn(en_name, zh_name):
        en = [w.strip() for w in en_name.split("/")]
        zh = [w.strip() for w in zh_name.split("|")]
        if len(en) == len(zh):
            for e, z in zip(en, zh):
                if e and z and z != e:
                    tr[e].add(z)

    for c in bad:
        p = by_handle.get(handle_of(c))
        if p:
            learn(en_colour(p), c["colors"][0]["name"])

    def word_ok(e, z):
        return z == e or z in tr.get(e, ())

    def score(zh_name, p, all_zh):
        """None = 有詞明確衝突(不是同一個商品);否則回傳「有證據吻合的詞數」。"""
        zh = [w.strip() for w in zh_name.split("|")]
        en = [w.strip() for w in en_colour(p).split("/")]
        if len(zh) != len(en):
            return None
        ev = 0
        for e, z in zip(en, zh):
            if word_ok(e, z):
                ev += 1
            elif z.isascii() or z in all_zh:
                return None  # 這個詞是別的英文詞的翻譯(或不同英文)=> 不是同一個顏色
        return ev if ev >= max(1, len(en) - 1) else None

    def match_card(c):
        """回傳 [(舊顏色, 官網商品或None, 平手數)];官網商品同一張卡內不重複使用。"""
        gender = "w" if c["name"].startswith("女款") else ("m" if c["name"].startswith("男款") else None)
        cand = by_title.get(norm(c["name"]), [])
        if gender == "w":
            cand = [p for p in cand if "ウィメンズ" in (p.get("tags") or [])]
        elif gender == "m":
            cand = [p for p in cand if "ウィメンズ" not in (p.get("tags") or [])]
        all_zh = set().union(*tr.values()) if tr else set()
        used = set()
        order = sorted(range(len(c["colors"])), key=lambda i: i != 0)
        res = {}
        for i in order:
            old = c["colors"][i]
            p, namb = None, 0
            first = by_handle.get(handle_of(c))
            if i == 0 and first is not None and first in cand:
                p = first
            else:
                sc = [(score(old["name"], q, all_zh), q) for q in cand if q["handle"] not in used]
                sc = [(s_, q) for s_, q in sc if s_ is not None]
                if sc:
                    top = max(s_ for s_, _ in sc)
                    tops = [q for s_, q in sc if s_ == top]
                    if len(tops) == 1:
                        p = tops[0]
                    else:
                        namb = len(tops)
            if p is not None:
                used.add(p["handle"])
            res[i] = (old, p, namb)
        return [res[i] for i in range(len(c["colors"]))]

    for _round in range(6):
        before = sum(len(v) for v in tr.values())
        for c in bad:
            for old, p, _ in match_card(c):
                if p is not None:
                    learn(en_colour(p), old["name"])
        if sum(len(v) for v in tr.values()) == before:
            break
    print("學到的顏色詞(英->中)", len(tr))

    rows, changed, near_miss = [], [], []
    covered = set(standalone_handles)
    tot = dict(cards=0, old=0, kept=0, dup_removed=0, dup_restored=0, ordered_oos=0,
               unmatched=0, hidden=0, ambiguous=0)

    def build_colour(old, p):
        sizes, stock = [], {}
        for v in p["variants"]:
            s_ = fix_size_key((v.get("option2") or v.get("option1") or "").strip())
            if not s_ or s_ in stock:
                continue
            sizes.append(s_)
            stock[s_] = 5 if v.get("available") else 0
        img = (p.get("images") or [{}])[0].get("src") or old.get("image")
        return {"name": old["name"], "image": img, "sizes": sizes, "stock": stock,
                "handle": p["handle"], "price": p["variants"][0].get("price")}

    for c in bad:
        kept, dups, oos, unmatched, amb = [], [], [], [], 0
        for old, p, namb in match_card(c):
            if namb:
                amb += 1
            if p is None:
                if (c["id"], old["name"]) in ordered:
                    # 客人買過、官網已找不到:保留,全部尺寸標缺貨
                    szs = list(old.get("sizes") or [])
                    oos.append({"name": old["name"], "image": old.get("image"), "sizes": szs,
                                "stock": {s_: 0 for s_ in szs}})
                else:
                    unmatched.append(old["name"])
                    near_miss.append((c["name"], old["name"], f"同標題官網商品 {len(by_title.get(norm(c['name']), []))} 個"))
                continue
            entry = build_colour(old, p)
            covered.add(p["handle"])
            if p["handle"] in standalone_handles and p["handle"] != handle_of(c):
                dups.append(entry)
                continue
            kept.append(entry)
        restored = 0
        if not kept and not oos and dups:
            # 官網還在賣的商品不能因為合併卡而被隱藏:整張卡只剩重複色時,把重複色放回來
            kept, restored, dups = dups, len(dups), []
        final = kept + oos
        tot["cards"] += 1; tot["old"] += len(c["colors"]); tot["kept"] += len(kept)
        tot["dup_removed"] += len(dups); tot["dup_restored"] += restored
        tot["ordered_oos"] += len(oos); tot["unmatched"] += len(unmatched); tot["ambiguous"] += amb
        # 官網還有同名商品 => 不隱藏、也不動這張卡(只隱藏官網整個系列都已下架的)
        protected = (not final) and bool(by_title.get(norm(c["name"])))
        hide = (not final) and not protected
        if protected:
            print("PROTECTED(官網同標題還有商品,這張卡不動)", c["id"], c["name"])
        if hide:
            print("HIDDEN_CHECK", c["id"], c["name"], "官網同標題商品數", len(by_title.get(norm(c["name"]), [])), "link還在官網", handle_of(c) in by_handle)
        tot["hidden"] += hide
        rows.append((c["id"], c["name"], len(c["colors"]), len(kept), restored, len(oos),
                     len(dups), len(unmatched), amb, hide))
        if APPLY:
            if final:
                c["colors"] = [{k: v for k, v in k_.items() if k not in ("handle", "price")} for k_ in final]
                c["image"] = final[0]["image"]
                if kept:
                    c["link"] = "https://salomon.jp/products/" + kept[0]["handle"]
                    try:
                        c["jpy"] = int(float(kept[0]["price"]))
                    except (TypeError, ValueError):
                        pass
            elif hide:
                c["hidden"] = True
            else:
                continue
            changed.append(c)

    uncovered = [q for h, q in by_handle.items() if h not in covered]
    print("UNCOVERED 官網有、但站上沒有任何卡片的商品數", len(uncovered))
    for q in uncovered[:40]:
        print("UNCOV", q["handle"], q["title"], en_colour(q))
    # 風險檢查:有「對不到的舊顏色」的卡,官網同標題是否還有「站上沒有任何卡片」的商品(可能是對錯字漏掉的活商品)
    unc_by_title = defaultdict(list)
    for q in uncovered:
        unc_by_title[norm(q["title"])].append(q)
    risk_cards = risk_cols = 0
    for r in rows:
        if r[7] > 0:
            n_unc = len(unc_by_title.get(norm(r[1]), []))
            if n_unc:
                risk_cards += 1; risk_cols += r[7]
                print("RISK", r[0], r[1], "對不到", r[7], "官網同標題但站上沒卡", n_unc)
    print("RISK_TOTAL cards", risk_cards, "colours", risk_cols)
    print("ID\tNAME\tOLD\tKEPT\tDUP_RESTORED\tORDERED_OOS\tDUP_REMOVED\tUNMATCHED\tAMBIG\tHIDE")
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
