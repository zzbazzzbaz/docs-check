"""页面设置 / 分节 / 页眉页脚对账：自研 vs WPS。

    python -m docxfmt.pages_compare [--report]

数据：`out/<篇名>.ownpages.json` 与 `<篇名>.wpspages.json`。节按 index 配对。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from .common import OUT, approx, first_family, norm_text, read_json
from .compare import canon_text, pair_by_occurrence, own_first

ALIGN = {0: "left", 1: "center", 2: "right", 3: "both", 4: "distribute"}

PAGE_KEYS = [("页宽", "w_pt"), ("页高", "h_pt"), ("方向", "orientation"),
             ("上边距", "top_pt"), ("下边距", "bottom_pt"), ("左边距", "left_pt"),
             ("右边距", "right_pt"), ("页眉距", "header_pt"), ("页脚距", "footer_pt")]

FIELDS = ["节数"] + [f[0] for f in PAGE_KEYS] + [
    "页码格式", "首页不同", "奇偶页不同",
    "页眉页脚文本", "本节自有引用", "PAGE域数",
    "页眉页脚中文字体", "页眉页脚西文字体", "页眉页脚字号", "页眉页脚对齐",
]

TOL = {"页宽": 1.0, "页高": 1.0, "上边距": 0.6, "下边距": 0.6, "左边距": 0.6,
       "右边距": 0.6, "页眉距": 0.6, "页脚距": 0.6, "页眉页脚字号": 0.2}


def eq(field, a, b) -> bool:
    if a is None or b is None:
        return a == b
    if field in TOL:
        return approx(a, b, TOL[field])
    return a == b


def collect():
    dist = defaultdict(Counter)
    samples = defaultdict(list)

    def add(field, ov, wv, where):
        dist[field][(ov, wv)] += 1
        if not eq(field, ov, wv) and len(samples[field]) < 12:
            samples[field].append((ov, wv, where))

    for wf in sorted(OUT.glob("*.wpspages.json")):
        stem = wf.name[: -len(".wpspages.json")]
        of = OUT / f"{stem}.ownpages.json"
        if not of.exists():
            continue
        own, wps = read_json(of), read_json(wf)
        os_, ws = own["sections"], wps["sections"]

        add("节数", len(os_), len(ws), stem)
        for i, o in enumerate(os_):
            if i >= len(ws):
                break
            W = ws[i]
            where = f"{stem[:18]} 第{i + 1}节"

            for label, key in PAGE_KEYS:
                add(label, o["page"].get(key), W["page"].get(key), where)
            add("页码格式", o["page_number_format"], W["page_number_format"], where)
            for label, key in (("首页不同", "different_first_page"),
                               ("奇偶页不同", "odd_and_even_pages")):
                ov, wv = o.get(key), W.get(key)
                if wv is not None:
                    add(label, bool(ov), bool(wv), where)

            for kind in ("headers", "footers"):
                for o_hf, w_hf in zip(o[kind], W[kind]):
                    whe = f"{where} {w_hf['type']}{kind[:6]}"
                    # 本节是否自己拥有该页眉/页脚（第一节 WPS 恒报假，见 README）
                    owns = bool(o_hf["has_reference"]) and w_hf.get("link_to_previous") is False
                    # 含 PAGE 域的页眉页脚不可比：WPS 报实时页码，自研只能读 XML 里缓存的域结果
                    if not (o_hf.get("page_fields") or w_hf.get("page_fields")):
                        add("页眉页脚文本", canon_text(o_hf["text"]),
                            canon_text(w_hf["text"]), whe)
                    if i:
                        add("本节自有引用", bool(o_hf["has_reference"]), owns, whe)
                    # 继承来的页眉页脚，WPS 的 Fields 只数本节自己的对象（报 0），只能在本节自有时比
                    if w_hf.get("page_fields") is not None and owns:
                        add("PAGE域数", o_hf["page_fields"], w_hf["page_fields"], whe)

                    op = [p for p in o_hf["paragraphs"] if norm_text(p["text"])]
                    wp = [p for p in w_hf["paragraphs"] if norm_text(p["text"])]
                    for oi, wi in pair_by_occurrence(op, wp):
                        ro, rw = op[oi], wp[wi]
                        o_ea = first_family(own_first(ro, "east", "ea") or "")
                        w_ea = first_family(rw.get("font_ea") or "")
                        # WPS 对继承来的页眉页脚也返回空字体名（未定义），不可比
                        if w_ea or not o_ea:
                            add("页眉页脚中文字体", o_ea, w_ea, whe)
                        add("页眉页脚西文字体", first_family(own_first(ro, "west", "ascii") or ""),
                            first_family(rw.get("font_ascii") or ""), whe)
                        add("页眉页脚字号", round(own_first(ro, "east", "size")
                                             or own_first(ro, "west", "size") or 0, 1),
                            round(rw.get("size") or 0, 1), whe)
                        add("页眉页脚对齐", ro["align"], ALIGN.get(rw.get("align"), rw.get("align")), whe)
    return dist, samples


def main() -> None:
    dist, samples = collect()
    if not dist:
        print("没有 out/*.wpspages.json —— 先跑 ./run.sh")
        return

    print("=== 页面设置 / 分节 / 页眉页脚：自研 vs WPS ===\n")
    tot = ok = 0
    for fld in FIELDS:
        rows = dist.get(fld)
        if not rows:
            continue
        n = sum(rows.values())
        o = sum(v for (a, b), v in rows.items() if eq(fld, a, b))
        tot += n
        ok += o
        flag = "" if o == n else "  ←"
        print(f"{fld:<18}{n:>7}{o:>7} ({o / n * 100:6.2f}%){flag}")

    print(f"\n{'合计':<18}{tot:>7}{ok:>7} ({ok / tot * 100:6.2f}%)")

    if "--report" in sys.argv:
        print("\n=== 不一致样例 ===")
        for fld in FIELDS:
            if not samples.get(fld):
                continue
            print(f"\n【{fld}】")
            for ov, wv, where in samples[fld][:6]:
                print(f"   {where:<26} 自研={ov!r:<22} WPS={wv!r}")


if __name__ == "__main__":
    main()
