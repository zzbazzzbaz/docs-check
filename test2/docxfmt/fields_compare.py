"""域与 TOC 跨度对账：自研 vs WPS。

    python -m docxfmt.fields_compare [--report]

数据：`out/<篇名>.own.json`（`fields` 与每段的 `field_codes`）与 `<篇名>.wpsfields.json`。
逐段比对按位置对齐（WPS 段号 = 自研段号 + 之前的表格行末标记数 + 1）。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from .common import OUT, read_json

FIELDS = ["域总数", "域代码分布", "TOC域跨度", "本段有域", "本段域代码"]


def codes(r) -> tuple:
    return tuple(sorted(r.get("field_codes") or []))


def collect():
    dist = defaultdict(Counter)
    samples = defaultdict(list)

    def add(field, ov, wv, where):
        dist[field][(ov, wv)] += 1
        if ov != wv and len(samples[field]) < 12:
            samples[field].append((ov, wv, where))

    for wf in sorted(OUT.glob("*.wpsfields.json")):
        stem = wf.name[: -len(".wpsfields.json")]
        of = OUT / f"{stem}.own.json"
        if not of.exists():
            continue
        own, wps = read_json(of), read_json(wf)
        o_fields = own.get("fields") or []
        w_fields = wps.get("fields") or []
        o_all = [r for r in own["paragraphs"] if r["story"] == "main"]

        # 自研段号（0 起）→ WPS 段号（1 起，且每个表格行末多一段）
        i2w, marks = {}, 0
        for i, r in enumerate(o_all):
            i2w[i] = i + marks + 1
            if r.get("row_end"):
                marks += 1
        w2i = {v: k for k, v in i2w.items()}

        add("域总数", len(o_fields), len(w_fields), stem)
        add("域代码分布", tuple(sorted(f.get("code") for f in o_fields)),
            tuple(sorted(f.get("code") for f in w_fields)), stem)

        # TOC 域跨度（两边都换成自研段号再比）
        def to_own(p):
            return w2i.get(p)

        o_toc = [(f["para"], f.get("end_para_content", f["end_para"]))
                 for f in o_fields if f.get("code") == "TOC"]
        w_toc = [(to_own(t.get("para")), to_own(t.get("end_para")))
                 for t in (wps.get("toc_spans") or [])]
        for n, (a, b) in enumerate(zip(o_toc, w_toc)):
            add("TOC域跨度", a, b, f"{stem[:16]} 第{n + 1}个TOC域")

        # 逐段（含合成域，与 WPS 的口径对齐）
        def by_para(fl):
            d = defaultdict(list)
            for f in fl:
                d[f.get("para")].append(f.get("code"))
            return d

        o_by = by_para(o_fields)
        w_by_p = by_para(w_fields)
        w_by = defaultdict(list)
        for p, codes in w_by_p.items():
            w_by[to_own(p)].extend(codes)
        for i, r in enumerate(o_all):
            o_codes = tuple(sorted(o_by.get(i, [])))
            w_codes = tuple(sorted(w_by.get(i, [])))
            where = f"{stem[:16]} 第{i + 1}段"
            add("本段有域", bool(o_codes), bool(w_codes), where)
            if o_codes or w_codes:
                add("本段域代码", o_codes, w_codes, where)
    return dist, samples


def main() -> None:
    dist, samples = collect()
    if not dist:
        print("没有 out/*.wpsfields.json —— 先跑 ./run.sh")
        return

    print("=== 域与 TOC 跨度：自研 vs WPS ===\n")
    tot = ok = 0
    for fld in FIELDS:
        rows = dist.get(fld)
        if not rows:
            continue
        n = sum(rows.values())
        o = sum(v for (a, b), v in rows.items() if a == b)
        tot += n
        ok += o
        print(f"{fld:<14}{n:>7}{o:>7} ({o / n * 100:6.2f}%){'' if o == n else '  ←'}")

    print(f"\n{'合计':<14}{tot:>7}{ok:>7} ({ok / tot * 100:6.2f}%)")

    if "--report" in sys.argv:
        print("\n=== 不一致样例 ===")
        for fld in FIELDS:
            if not samples.get(fld):
                continue
            print(f"\n【{fld}】")
            for ov, wv, where in samples[fld][:6]:
                print(f"   {where:<26} 自研={ov!r:<34} WPS={wv!r}")


if __name__ == "__main__":
    main()
