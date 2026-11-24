# -*- coding: utf-8 -*-
"""On(on.com)顏色名稱:官網英文 → 站上用的中文。

2026-11-24:On 的商品卡原本每個顏色都用同一張圖,每日同步是靠「圖片」去對官網的顏色,
對不到就把整張卡庫存歸零(650 張裡 259 張全缺貨,抽查多張官網其實有貨)。改成同步時
直接依官網 hasVariant 重建顏色清單(每色自己的圖、sku、尺寸庫存)。

顏色名稱:On 的色名常常跟字面意思不符(見 memory on-color-names-not-literal,
Ember=暖灰、Acai=灰藍…),所以這裡「只收有足夠證據」的對照——來自 2026-07-17 逐色看圖
修正過、目前存在 Firebase 裡的中文名,跟官網現在的顏色用多輪比對學出來,且只留出現 ≥3 次、
一致性 ≥80% 的詞。查不到的詞維持官網英文原名,不亂猜。
"""

ON_COLOR_ZH = {
    "Ivory": "象牙白", "Glacier": "冰川灰", "Black": "黑", "Iceberg": "冰山灰", "Sakura": "櫻花粉",
    "Lime": "萊姆綠", "Blue": "藍", "Toffee": "太妃糖棕", "Green": "綠", "Rock": "岩石灰",
    "Caper": "淺綠", "Dew": "露白", "Pink": "粉紅", "Shadow": "陰影灰", "Malibu": "馬里布藍",
    "Iron": "鐵灰", "Sienna": "赭石棕", "Grizzly": "灰熊棕", "Pearl": "珍珠白", "Pacific": "太平洋藍",
    "Chambray": "錢布雷藍", "Multicolor": "多彩", "White": "白", "Flurry": "薄荷白",
    "Juniper": "紫羅蘭色", "Celeste": "天藍色", "Frost": "霜白色", "Eclipse": "墨灰", "Ice": "冰色",
    "Raspberry": "覆盆莓粉", "Bloom": "淡紫色", "Ghost": "幽白", "Olive": "橄欖綠", "Sailor": "水手藍",
    "Mineral": "礦石色", "Tin": "錫灰", "Alloy": "合金灰", "Flame": "火焰橘", "Silver": "銀",
    "Midnight": "午夜藍", "Fog": "米灰色", "Camellia": "山茶花色", "Obsidian": "黑曜石",
    "Magnet": "磁灰", "Arctic": "極地白", "Navy": "深藍", "Wash": "水洗藍", "Ember": "餘燼灰",
    "Brume": "薄霧灰", "Acai": "灰藍色", "Thistle": "薊花紫", "Clove": "丁香棕",
}


def halves(name):
    return [h.strip() for h in (name or "").split("|")]


def translate_on_color(name):
    """'Ivory | Dustrose' → '象牙白 | Dustrose'(查不到的詞保留英文)。"""
    return " | ".join(ON_COLOR_ZH.get(h, h) for h in halves(name))


def assign_names(live_colors, old_names):
    """替每個官網顏色決定站上顯示名稱。

    live_colors: 官網顏色字串清單(順序同 hasVariant);old_names: 資料庫裡舊顏色名稱
    (舊資料沒有 sku,只能靠名稱)。能唯一對上的舊名稱優先沿用(保住當初逐色看圖確認過的
    翻譯),對不上的用字典翻、字典沒有的詞保留英文。
    「唯一對上」= 片段數相同、已知詞全部吻合、至少有一個已知詞、而且這個官網顏色只有這
    一個舊名稱可能、這個舊名稱也只有這一個官網顏色可能。"""
    local = dict(ON_COLOR_ZH)  # 全域字典 + 這張卡本身已唯一配對出來的詞(迭代,越配越多)
    matched = {}  # 官網顏色 index → 舊名稱 index
    for _ in range(6):
        cands = {}
        for i, lc in enumerate(live_colors):
            if i in matched:
                continue
            ha = halves(lc)
            cs = []
            for j, old in enumerate(old_names):
                if j in matched.values():
                    continue
                hb = halves(old)
                if len(hb) != len(ha):
                    continue
                known = 0
                ok = True
                for e, z in zip(ha, hb):
                    if e in local:
                        if local[e] != z:
                            ok = False
                            break
                        known += 1
                if ok and known >= 1:
                    cs.append(j)
            cands[i] = cs
        progress = False
        for i, cs in cands.items():
            if len(cs) == 1 and sum(1 for k in cands.values() if cs[0] in k) == 1:
                matched[i] = cs[0]
                for e, z in zip(halves(live_colors[i]), halves(old_names[cs[0]])):
                    local.setdefault(e, z)
                progress = True
        if not progress:
            break
    return [old_names[matched[i]] if i in matched else translate_on_color(lc)
            for i, lc in enumerate(live_colors)]
