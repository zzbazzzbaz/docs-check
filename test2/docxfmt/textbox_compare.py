"""文本框内容对账：自研 vs WPS。

    python -m docxfmt.textbox_compare [--report]

配对方式：按 `anchor_para` 对齐（两边都换算成自研段号）+ 出现次序，
不按框的枚举次序 —— WPS 的 `Shapes` 次序与 OOXML 的文档次序不一定一致。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from .common import OUT, approx, first_family, read_json
from .compare import canon_text

ALIGN = {0: "left", 1: "center", 2: "right", 3: "both", 4: "distribute"}

FIELDS = ["框数", "锚定段号", "文本", "段数", "中文字体", "西文字体", "字号", "对齐", "编号"]
TOL = {"字号": 0.2}


def eq(field, a, b) -> bool:
    if field in TOL:
        return approx(a or 0, b or 0, TOL[field])
    return a == b


def collect():
    dist = defaultdict(Counter)
    samples = defaultdict(list)

    def add(field, ov, wv, where):
        dist[field][(ov, wv)] += 1
        if not eq(field, ov, wv) and len(samples[field]) < 12:
            samples[field].append((ov, wv, where))

    for wf in sorted(OUT.glob("*.wpstextbox.json")):
        stem = wf.name[: -len(".wpstextbox.json")]
        of = OUT / f"{stem}.owntextbox.json"
        og = OUT / f"{stem}.own.json"
        if not (of.exists() and og.exists()):
            continue
        own, wps = read_json(of), read_json(wf)

        # WPS 段号（1 起，含表格行末标记）→ 自研段号
        o_all = [r for r in read_json(og)["paragraphs"] if r["story"] == "main"]
        i2w, marks = {}, 0
        for i, r in enumerate(o_all):
            i2w[i] = i + marks + 1
            if r.get("row_end"):
                marks += 1
        w2i = {v: k for k, v in i2w.items()}

        add("框数", own["counts"]["boxes"], wps["counts"]["boxes"], stem)

        ob = {(b["anchor_para"], n): b for n, b in enumerate(own["boxes"])}
        wb = {(w2i.get(b["anchor_para"]), n): b for n, b in enumerate(wps["boxes"])}
        for key, o in ob.items():
            w = wb.get(key)
            if w is None:
                continue
            where = f"{stem[:16]} 框@{key[0]}"
            add("锚定段号", o["anchor_para"], key[0], where)
            add("文本", canon_text(o["text"]), canon_text(w.get("text") or ""), where)
            op, wp = o["paragraphs"], w.get("paragraphs") or []
            add("段数", len(op), len(wp), where)
            for p, q in zip(op, wp):
                add("中文字体", first_family(p.get("font_ea") or ""),
                    first_family(q.get("font_ea") or ""), where)
                add("西文字体", first_family(p.get("font_ascii") or ""),
                    first_family(q.get("font_ascii") or ""), where)
                add("字号", round(p.get("size") or 0, 1), round(q.get("size") or 0, 1), where)
                add("对齐", p.get("align"), ALIGN.get(q.get("align"), q.get("align")), where)
                add("编号", p.get("list_type") is not None,
                    (q.get("list_type") or 0) != 0, where)
    return dist, samples


def main() -> None:
    dist, samples = collect()
    if not dist:
        print("没有 out/*.wpstextbox.json —— 先跑 ./run.sh")
        return

    print("=== 文本框内容：自研 vs WPS ===\n")
    tot = ok = 0
    for fld in FIELDS:
        rows = dist.get(fld)
        if not rows:
            continue
        n = sum(rows.values())
        o = sum(v for (a, b), v in rows.items() if eq(fld, a, b))
        tot += n
        ok += o
        print(f"{fld:<10}{n:>6}{o:>6} ({o / n * 100:6.2f}%){'' if o == n else '  ←'}")

    print(f"\n{'合计':<10}{tot:>6}{ok:>6} ({ok / tot * 100:6.2f}%)")

    if "--report" in sys.argv:
        print("\n=== 不一致样例 ===")
        for fld in FIELDS:
            if not samples.get(fld):
                continue
            print(f"\n【{fld}】")
            for ov, wv, where in samples[fld][:6]:
                print(f"   {where:<24} 自研={ov!r:<28} WPS={wv!r}")


if __name__ == "__main__":
    main()
