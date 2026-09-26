"""段落样式名对账：自研 vs aspose-words-foss。

WPS 取不到样式名（`para.Style` 是裸 `IDispatch`），所以这一项**没有真值裁判**，
只能用「两个独立实现读同一份 `styles.xml`」互证 —— 强度低于其它对账，但能抓实现 bug。

样式名是 `TOC-07/12/13/14/15`、`APP-13`、`REF/ACK/APP-04` 那批规则的前置（目录条目/标题的筛选）。

    python -m docxfmt.style_compare [--report]
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict

from .common import OUT, read_json
from .compare import pair_by_occurrence

TOC_STYLE = re.compile(r"^toc\s*[123]$")
HEADING_STYLE = re.compile(r"^heading\s*\d+$")

FIELDS = ["段落样式名", "目录条目数（toc N）", "标题数（heading N）"]


def norm(name) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def toc_entries(paras, toc_spans) -> int:
    """TOC 域跨度内、样式名 ∈ {toc 1,2,3} 的段落数（`TOC-07`~`TOC-15` 的条目筛选）。"""
    n = 0
    for r in paras:
        if not TOC_STYLE.match(norm(r.get("style_name"))):
            continue
        p = r.get("ordinal")
        if any(a <= p <= b for a, b in toc_spans):
            n += 1
    return n


def collect():
    dist = defaultdict(Counter)
    samples = defaultdict(list)
    skipped: Counter = Counter()      # foss 无法判定的段落（没写 pStyle）

    def add(field, ov, wv, where):
        dist[field][(ov, wv)] += 1
        if ov != wv and len(samples[field]) < 12:
            samples[field].append((ov, wv, where))

    for ff in sorted(OUT.glob("*.foss.json")):
        stem = ff.name[: -len(".foss.json")]
        of = OUT / f"{stem}.own.json"
        if not of.exists():
            continue
        own, fos = read_json(of), read_json(ff)
        om = [r for r in own["paragraphs"] if r["story"] == "main" and (r["text"] or "").strip()]
        fm = [r for r in fos["paragraphs"] if r["story"] == "main" and (r["text"] or "").strip()]
        pairs = pair_by_occurrence(om, fm)

        for oi, fi in pairs:
            o_style, f_style = norm(om[oi].get("style_name")), norm(fm[fi].get("style_name"))
            # foss 对「没写 pStyle」的段落不套默认段落样式（它的已知缺陷），这种它给不出值
            if not f_style:
                skipped[stem] += 1
            else:
                add("段落样式名", o_style, f_style, f"{stem[:20]}")

        # 派生量：规则真正要的两类段落计数（两边各自算，再比）
        o_spans = [(f["para"], f.get("end_para_content", f["end_para"]))
                   for f in (own.get("fields") or []) if f.get("code") == "TOC"]
        f_spans = [(f["para"], f["end_para"]) for f in (fos.get("fields") or [])
                   if f.get("code") == "TOC"] if fos.get("fields") else []
        add("目录条目数（toc N）", toc_entries(own["paragraphs"], o_spans),
            toc_entries(fos["paragraphs"], f_spans or o_spans), stem)
        add("标题数（heading N）",
            sum(1 for r in own["paragraphs"] if HEADING_STYLE.match(norm(r.get("style_name")))),
            sum(1 for r in fos["paragraphs"] if HEADING_STYLE.match(norm(r.get("style_name")))),
            stem)
    return dist, samples, sum(skipped.values())


def main() -> None:
    dist, samples, skipped = collect()
    if not dist:
        print("没有 out/*.foss.json —— 先跑 ./run.sh")
        return

    print("=== 段落样式名：自研 vs foss（无 WPS 裁判，独立实现互证）===\n")
    tot = ok = 0
    for fld in FIELDS:
        rows = dist.get(fld)
        if not rows:
            continue
        n = sum(rows.values())
        o = sum(v for (a, b), v in rows.items() if a == b)
        tot += n
        ok += o
        print(f"{fld:<20}{n:>7}{o:>7} ({o / n * 100:6.2f}%){'' if o == n else '  ←'}")

    print(f"\n{'合计':<20}{tot:>7}{ok:>7} ({ok / tot * 100:6.2f}%)")
    print(f"foss 无法判定的段落（没写 pStyle，它不套默认样式）：{skipped}")

    if "--report" in sys.argv:
        print("\n=== 不一致样例 ===")
        for fld in FIELDS:
            if not samples.get(fld):
                continue
            print(f"\n【{fld}】")
            for ov, wv, where in samples[fld][:8]:
                print(f"   {where:<26} 自研={ov!r:<22} foss={wv!r}")


if __name__ == "__main__":
    main()
