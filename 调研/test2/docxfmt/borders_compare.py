"""表格边框对账：自研 vs WPS。

    python -m docxfmt.borders_compare [--report]

两边都按「单元格四边有没有线」比（前 2 行 × 前 3 列，与取值脚本一致）。
WPS 的 `style` 取 9999999（未定义）时跳过（超链接/合并视图里的边界会给这个）。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from .common import OUT, read_json

EDGES = ("top", "left", "bottom", "right")
FIELDS = ["表数", "行数", "列数"] + [f"单元格{e}" for e in EDGES]


def wps_exists(edge) -> bool | None:
    """WPS 的 {style,width} → 有没有线；None/9999999 表示未定义。"""
    if edge is None:
        return None
    s = edge.get("style")
    if s is None or s == 9999999:
        return None
    return s != 0


def collect():
    dist = defaultdict(Counter)
    samples = defaultdict(list)

    def add(field, ov, wv, where):
        dist[field][(ov, wv)] += 1
        if ov != wv and len(samples[field]) < 12:
            samples[field].append((ov, wv, where))

    for wf in sorted(OUT.glob("*.wpsborders.json")):
        stem = wf.name[: -len(".wpsborders.json")]
        of = OUT / f"{stem}.ownborders.json"
        if not of.exists():
            continue
        own, wps = read_json(of), read_json(wf)
        ot, wt = own["tables"], wps.get("tables") or []
        add("表数", len(ot), wps.get("counts", {}).get("tables"), stem)

        for o, w in zip(ot, wt):
            where = f"{stem[:16]} 表{o['i']}"
            add("行数", o["rows"], w.get("rows"), where)
            add("列数", o["cols"], w.get("cols"), where)
            wcell = {(c["r"], c["c"]): c["edges"] for c in (w.get("cells") or [])}
            for c in o["cells"]:
                we = wcell.get((c["r"], c["c"]))
                if we is None:
                    continue
                for e in EDGES:
                    wv = wps_exists(we.get(e))
                    if wv is None:
                        continue
                    where2 = f"{where} r{c['r']}c{c['c']}"
                    add(f"单元格{e}", c["edges"][e], wv, where2)
    return dist, samples


def main() -> None:
    dist, samples = collect()
    if not dist:
        print("没有 out/*.wpsborders.json —— 先跑 ./run.sh")
        return

    print("=== 表格边框：自研 vs WPS（单元格四边有没有线）===\n")
    tot = ok = 0
    for fld in FIELDS:
        rows = dist.get(fld)
        if not rows:
            continue
        n = sum(rows.values())
        o = sum(v for (a, b), v in rows.items() if a == b)
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
                print(f"   {where:<30} 自研={ov!r:<8} WPS={wv!r}")


if __name__ == "__main__":
    main()
