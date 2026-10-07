"""图片 / 公式对象对账：自研 vs WPS。

    python -m docxfmt.objects_compare [--report]

数据：`out/<篇名>.own.json`（对象计数在每段的 `objects` 里）与 `<篇名>.wpsobjects.json`。
逐段比对按位置对齐：WPS 的 Paragraphs 在每个表格行末多一个空段落，用自研的 `row_end` 补回去。
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict

from .common import OUT, read_json
from .compare import canon_text

# 规则里图题的识别口径：可见文本以「图 + 章号-序号」开头
CAPTION = re.compile(r"^图\s*\d+\s*-\s*\d+")
ZW = "\u200b"          # 有些文档会把零宽空格塞在开头

FIELDS = ["内嵌图形数", "浮动图形数", "表格数", "OLE公式数", "OMML公式数",
          "本段含内嵌对象", "本段含浮动对象", "本段含OMML", "图题前一段是图"]


def counts(objs) -> int:
    """对齐 WPS 的 InlineShapes：wp:inline + 内嵌 VML + OLE 对象。"""
    return objs["inline"] + objs["pict_inline"] + objs["ole"]


def floats(objs) -> int:
    """对齐 WPS 的 Shapes：wp:anchor + 浮动 VML。"""
    return objs["anchor"] + objs["pict_float"]


def collect():
    dist = defaultdict(Counter)
    samples = defaultdict(list)

    def add(field, ov, wv, where):
        dist[field][(ov, wv)] += 1
        if ov != wv and len(samples[field]) < 12:
            samples[field].append((ov, wv, where))

    for wf in sorted(OUT.glob("*.wpsobjects.json")):
        stem = wf.name[: -len(".wpsobjects.json")]
        of = OUT / f"{stem}.own.json"
        wpf = OUT / f"{stem}.wps.json"
        if not (of.exists() and wpf.exists()):
            continue
        own, wps = read_json(of), read_json(wf)
        # wpsobjects.json 只有计数没有文本，图题判定要用 wps.json 的文本（两者段落序一致）
        wps_texts = [r.get("text") or "" for r in read_json(wpf)["paragraphs"]]
        o_all = [r for r in own["paragraphs"] if r["story"] == "main"]
        w_all = wps["paragraphs"]
        c = wps["counts"]

        # 每篇总数
        add("内嵌图形数", sum(counts(r["objects"]) for r in o_all), c.get("inline_shapes"), stem)
        add("浮动图形数", sum(floats(r["objects"]) for r in o_all), c.get("shapes"), stem)
        add("表格数", own["meta"].get("n_tables"), c.get("tables"), stem)
        add("OLE公式数", sum(r["objects"]["ole"] for r in o_all),
            (c.get("inline_by_type") or {}).get("1") or 0, stem)
        add("OMML公式数", sum(r["objects"]["omath"] for r in o_all), c.get("omaths"), stem)

        # 逐段：位置对齐（自研下标 + 之前的行末标记数 = WPS 下标）
        j = 0
        for i, r in enumerate(o_all):
            if j >= len(w_all):
                break
            W = w_all[j]
            where = f"{stem[:16]} 第{i + 1}段"
            add("本段含内嵌对象", counts(r["objects"]) > 0,
                (W.get("inline_shapes") or 0) > 0, where)
            add("本段含浮动对象", floats(r["objects"]) > 0, (W.get("shapes") or 0) > 0, where)
            add("本段含OMML", r["objects"]["omath"] > 0, (W.get("omaths") or 0) > 0, where)
            j += 2 if r.get("row_end") else 1

        # 图题在图下方：两边各自算出「图题段的前一段是不是图」，再按出现次序配对
        o_flags = [floats(o_all[i - 1]["objects"]) + counts(o_all[i - 1]["objects"]) > 0
                   for i in range(1, len(o_all))
                   if CAPTION.match(canon_text(o_all[i]["text"]).lstrip(ZW))]
        w_flags = [((w_all[k - 1].get("inline_shapes") or 0)
                    + (w_all[k - 1].get("shapes") or 0)) > 0
                   for k in range(1, len(w_all))
                   if CAPTION.match(canon_text(wps_texts[k]).lstrip(ZW))]
        for n, (a, b) in enumerate(zip(o_flags, w_flags)):
            add("图题前一段是图", a, b, f"{stem[:16]} 第{n + 1}个图题")
    return dist, samples


def main() -> None:
    dist, samples = collect()
    if not dist:
        print("没有 out/*.wpsobjects.json —— 先跑 ./run.sh")
        return

    print("=== 图片 / 公式对象：自研 vs WPS ===\n")
    tot = ok = 0
    for fld in FIELDS:
        rows = dist.get(fld)
        if not rows:
            continue
        n = sum(rows.values())
        o = sum(v for (a, b), v in rows.items() if a == b)
        tot += n
        ok += o
        print(f"{fld:<16}{n:>7}{o:>7} ({o / n * 100:6.2f}%){'' if o == n else '  ←'}")

    print(f"\n{'合计':<16}{tot:>7}{ok:>7} ({ok / tot * 100:6.2f}%)")

    if "--report" in sys.argv:
        print("\n=== 不一致样例 ===")
        for fld in FIELDS:
            if not samples.get(fld):
                continue
            print(f"\n【{fld}】")
            for ov, wv, where in samples[fld][:6]:
                print(f"   {where:<26} 自研={ov!r:<8} WPS={wv!r}")


if __name__ == "__main__":
    main()
