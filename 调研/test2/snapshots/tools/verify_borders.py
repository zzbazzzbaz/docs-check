"""核对 wpsborders.json 与 OOXML 真值，并找真三线表。

    cd test2 && uv run python out/verify_borders.py [篇名...]

比对口径：
  * 表级：WPS Table.Borders 6 边 vs「按单元格有效值合并」的 OOXML 模型
    （6 边，单元格间不一致时 WPS 报 9999999，模型也判 undefined）。
  * 单元：WPS Cell.Borders 4 边 vs OOXML 有效单元格边框。
    - direct 模型 = 表样式 tblPr/tblBorders ⊕ 直接 tblPr/tblBorders ⊕ tcBorders
    - std  模型 = 再叠加表样式 tblStylePr 条件格式（firstRow/lastRow/firstCol/lastCol）
    两份都算，看 WPS 更贴哪份 —— 判定 WPS 认不认条件格式。
  * 顺带验证：vMerge 与 Rows.Item(1)=None 的相关性、LineStyle 取值分布。
"""
import glob
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

OUT = Path(__file__).resolve().parent
CORPUS = OUT.parent / "corpus"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EDGES6 = ["top", "left", "bottom", "right", "insideH", "insideV"]
WKEY = {"insideH": "inside_h", "insideV": "inside_v"}
EDGES4 = ["top", "left", "bottom", "right"]


def q(t):
    return f"{{{W}}}{t}"


def wps_raw(edges, e):
    return (edges or {}).get(WKEY.get(e, e))


def wps_norm(e):
    """→ ("on",sz) | ("off",0|"unset") | ("undef",None) | None"""
    if not e:
        return None
    s, w = e.get("style"), e.get("width")
    if s == 9999999 or w == 9999999:
        return ("undef", None)
    if s in (None, 0):
        return ("off", 0 if w in (None, 0) else "unset")
    return ("on", w)


def parse_borders(el):
    if el is None:
        return {}
    out = {}
    for e in EDGES6:
        b = el.find(q(e))
        if b is None:
            continue
        val = b.get(q("val"))
        if val in (None, "nil", "none"):
            out[e] = ("off", 0)
        else:
            try:
                out[e] = ("on", int(b.get(q("sz")) or 4))
            except ValueError:
                out[e] = ("on", 4)
    return out


def merge_borders(base, over):
    r = dict(base)
    r.update(over)
    return r


def table_styles(styles_root):
    return {s.get(q("styleId")): s for s in styles_root.findall(q("style"))
            if s.get(q("type")) == "table"}


def resolve_style(sid, smap, seen=None):
    seen = seen or set()
    if sid in seen or sid not in smap:
        return {}, {}
    seen.add(sid)
    s = smap[sid]
    base, cond = {}, {}
    based = s.find(q("basedOn"))
    if based is not None:
        base, cond = resolve_style(based.get(q("val")), smap, seen)
    pr = s.find(q("tblPr"))
    if pr is not None:
        base = merge_borders(base, parse_borders(pr.find(q("tblBorders"))))
    for sp in s.findall(q("tblStylePr")):
        typ = sp.get(q("type"))
        b = {}
        tcpr = sp.find(q("tcPr"))
        trpr = sp.find(q("trPr"))
        if tcpr is not None:
            b = merge_borders(b, parse_borders(tcpr.find(q("tcBorders"))))
        if trpr is not None:
            b = merge_borders(b, parse_borders(trpr.find(q("tblBorders"))))
        if b:
            cond[typ] = merge_borders(cond.get(typ, {}), b)
    return base, cond


def oox_table(tbl, smap):
    """→ (sid, base, direct, cond)；direct/cond 均为 {edge: (presence,width)}"""
    pr = tbl.find(q("tblPr"))
    sid = None
    direct = {}
    if pr is not None:
        st = pr.find(q("tblStyle"))
        if st is not None:
            sid = st.get(q("val"))
        direct = parse_borders(pr.find(q("tblBorders")))
    base, cond = resolve_style(sid, smap) if sid else ({}, {})
    return sid, base, direct, cond


def grid_of(tbl):
    """→ (grid, nrows, ncols)。grid[(r,c)] = (tc, r0, r1, c0, c1)，覆盖合并区每个格子。"""
    trs = tbl.findall(q("tr"))
    raw = []
    for ri, tr in enumerate(trs, 1):
        col = 1
        for tc in tr.findall(q("tc")):
            tcpr = tc.find(q("tcPr"))
            span, vm = 1, None
            if tcpr is not None:
                gs = tcpr.find(q("gridSpan"))
                if gs is not None and gs.get(q("val")):
                    span = int(gs.get(q("val")))
                v = tcpr.find(q("vMerge"))
                if v is not None:
                    vm = v.get(q("val")) or "continue"
            raw.append({"tc": tc, "r": ri, "c0": col, "c1": col + span - 1, "vm": vm})
            col += span
    ncols = max((x["c1"] for x in raw), default=0)
    nrows = len(trs)
    grid = {}
    for cell in raw:
        if cell["vm"] == "continue":
            continue
        r1 = cell["r"]
        if cell["vm"] == "restart":
            for o in raw:
                if o["c0"] == cell["c0"] and o["r"] > cell["r"] and o["vm"] == "continue":
                    r1 = max(r1, o["r"])
        # vMerge 区可能跨多列，把同列后继行都算进来
        for o in raw:
            if o["r"] > cell["r"] and o["vm"] == "continue" and \
                    cell["c0"] <= o["c0"] <= cell["c1"]:
                r1 = max(r1, o["r"])
        for r in range(cell["r"], r1 + 1):
            for c in range(cell["c0"], cell["c1"] + 1):
                grid[(r, c)] = (cell["tc"], cell["r"], r1, cell["c0"], cell["c1"])
    return grid, nrows, ncols


def cell_edges(grid, r, c, nrows, ncols, tbl_eff, cond=None):
    """该 grid 位置的有效 4 边。位置不存在（gridAfter 缺格）时给全 off。"""
    if (r, c) not in grid:
        return {e: ("off", "unset") for e in EDGES4}
    tc, r0, r1, c0, c1 = grid[(r, c)]
    tcpr = tc.find(q("tcPr"))
    own = parse_borders(tcpr.find(q("tcBorders"))) if tcpr is not None else {}
    extra = {}
    if cond:
        if r0 == 1 and "firstRow" in cond:
            extra = merge_borders(extra, cond["firstRow"])
        if r1 == nrows and "lastRow" in cond:
            extra = merge_borders(extra, cond["lastRow"])
        if c0 == 1 and "firstCol" in cond:
            extra = merge_borders(extra, cond["firstCol"])
        if c1 == ncols and "lastCol" in cond:
            extra = merge_borders(extra, cond["lastCol"])
    spec = merge_borders(extra, own)

    def pick(edge, far, near):
        if edge in spec:
            return spec[edge]
        return tbl_eff.get(far) or tbl_eff.get(near) or ("off", "unset")

    return {
        "top": pick("top", "top" if r == r0 == 1 else "insideH", "insideH"),
        "bottom": pick("bottom", "bottom" if r == r1 == nrows else "insideH", "insideH"),
        "left": pick("left", "left" if c == c0 == 1 else "insideV", "insideV"),
        "right": pick("right", "right" if c == c1 == ncols else "insideV", "insideV"),
    }


def uniform(vals):
    if not vals:
        return ("undef", None)
    first = vals[0]
    return first if all(v == first for v in vals) else ("undef", None)


def wps_three(t) -> bool:
    """只看 WPS 侧信息判三线表：上下线 + 表头下线，无竖线/其它横线。"""
    def on(edges, e):
        n = wps_norm(wps_raw(edges, e))
        return n is not None and n[0] == "on"

    top = on(t["edges"], "top")
    bottom = on(t["edges"], "bottom")
    left = on(t["edges"], "left")
    right = on(t["edges"], "right")
    iv = on(t["edges"], "inside_v")
    ih = on(t["edges"], "inside_h")
    rows = t["rows"]
    r1 = [c for c in t["cells"] if c["r"] == 1 and c.get("edges")]
    r2 = [c for c in t["cells"] if c["r"] == 2 and c.get("edges")]
    if not top or not bottom or left or right or iv or not r1:
        return False
    # rows>=3 时 insideH=on 说明内部还有横线；rows==2 时 insideH 就是表头线
    if rows > 2 and ih:
        return False
    if not all(on(c["edges"], "bottom") for c in r1):
        return False
    # 第 2 行是内部行：底边应为无；只有 2 行时它是最后一行，底边即表底线
    if rows > 2 and r2 and not all(not on(c["edges"], "bottom") for c in r2):
        return False
    return True


def table_edges_model(grid, nrows, ncols, tbl_eff, cond=None):
    """按单元格有效值合并出 6 条表级边（与 WPS Table.Borders 同口径）。"""
    def val(r, c, e):
        ce = cell_edges(grid, r, c, nrows, ncols, tbl_eff, cond)
        return ce[e] if ce else None

    out = {
        "top": uniform([val(1, c, "top") for c in range(1, ncols + 1)]),
        "bottom": uniform([val(nrows, c, "bottom") for c in range(1, ncols + 1)]),
        "left": uniform([val(r, 1, "left") for r in range(1, nrows + 1)]),
        "right": uniform([val(r, ncols, "right") for r in range(1, nrows + 1)]),
        "insideH": uniform([val(r, c, "bottom") for r in range(1, nrows) for c in range(1, ncols + 1)]),
        "insideV": uniform([val(r, c, "right") for c in range(1, ncols) for r in range(1, nrows + 1)]),
    }
    return out


def label_of(w, o):
    if o is None:
        return "无对应单元格"
    if w is None and o is None:
        return "一致"
    if w is None:
        return "WPS缺"
    if o is None:
        return "OOXML缺"
    if w[0] == "undef" and o[0] == "undef":
        return "一致"
    if w[0] == "undef":
        return "WPS未定义"
    if o[0] == "undef":
        return "模型未定义"
    if w[0] == "off" and o[0] == "off":
        return "一致" if w[1] == o[1] else "均无(宽度表示不同)"
    if w[0] == "on" and o[0] == "on":
        return "一致" if w[1] == o[1] else "线宽不同"
    return "WPS有线/OOXML无线" if w[0] == "on" else "WPS无线/OOXML有线"


def main():
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = sorted(glob.glob(str(OUT / "*.wpsborders.json")))
    if only:
        files = [f for f in files if Path(f).name[: -len(".wpsborders.json")] in set(only)]

    tbl_direct = [0, 0]
    tbl_std = [0, 0]
    tbl_mism = []
    cell_direct = [0, 0]
    cell_std = [0, 0]
    cell_label_d = Counter()
    cell_label_s = Counter()
    cell_mism_std = []
    vm_corr = Counter()
    three = []
    three_set = set()
    wps_three_set = set()
    three_disagree = []
    per_table = []
    off_width = Counter()
    linestyle_cell = Counter()
    linestyle_tbl = Counter()
    off_vs_nil = Counter()

    for f in files:
        stem = Path(f).name[: -len(".wpsborders.json")]
        docx = CORPUS / f"{stem}.docx"
        if not docx.exists():
            print(f"!! 缺 corpus/{stem}.docx")
            continue
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        z = zipfile.ZipFile(docx)
        doc = etree.fromstring(z.read("word/document.xml"))
        smap = table_styles(etree.fromstring(z.read("word/styles.xml")))
        tbls = doc.find(q("body")).findall(q("tbl"))
        if j["counts"]["tables"] != len(tbls):
            print(f"!! {stem}: WPS表数 {j['counts']['tables']} != OOXML {len(tbls)}")
        for t in j["tables"]:
            i = t["i"]
            if i > len(tbls):
                continue
            tbl = tbls[i - 1]
            sid, base, direct, cond = oox_table(tbl, smap)
            eff_d = merge_borders(base, direct)
            eff_s = eff_d
            grid, nrows, ncols = grid_of(tbl)

            # 表级
            pt_tbl_ok = pt_tbl_tot = 0
            for tag, cfg, stat in (("direct", None, tbl_direct), ("std", cond, tbl_std)):
                model = table_edges_model(grid, nrows, ncols, eff_d, cfg)
                for e in EDGES6:
                    w = wps_norm(wps_raw(t["edges"], e))
                    o = model[e]
                    lb = label_of(w, o)
                    stat[1] += 1
                    if lb == "一致":
                        stat[0] += 1
                    if tag == "std":
                        pt_tbl_tot += 1
                        pt_tbl_ok += lb == "一致"
                        if lb != "一致" and len(tbl_mism) < 999:
                            tbl_mism.append((stem, i, e, w, o, lb, list(cond)))

            # 单元
            pt_cell_ok = pt_cell_tot = 0
            for cell in t["cells"]:
                r, c = cell["r"], cell["c"]
                od = cell_edges(grid, r, c, nrows, ncols, eff_d)
                os_ = cell_edges(grid, r, c, nrows, ncols, eff_d, cond)
                for e in EDGES4:
                    w = wps_norm(wps_raw(cell.get("edges"), e))
                    lbd = label_of(w, od[e])
                    cell_label_d[lbd] += 1
                    cell_direct[1] += 1
                    cell_direct[0] += lbd == "一致"
                    lbs = label_of(w, os_[e])
                    cell_label_s[lbs] += 1
                    cell_std[1] += 1
                    cell_std[0] += lbs == "一致"
                    pt_cell_tot += 1
                    pt_cell_ok += lbs == "一致"
                    if lbs != "一致" and len(cell_mism_std) < 999:
                        cell_mism_std.append((stem, i, r, c, e, w, os_[e], lbs, list(cond)))
            per_table.append((stem, i, t["rows"], t["cols"], sid, pt_tbl_ok, pt_tbl_tot,
                              pt_cell_ok, pt_cell_tot))

            has_vm = any(x.tag == q("vMerge") for x in tbl.iter())
            vm_corr[(has_vm, t["row1_edges"] is None)] += 1

            # 三线表判定（std 模型，全部用单元格有效值）
            def on(b):
                return b is not None and b[0] == "on"

            def ce(r, c):
                return cell_edges(grid, r, c, nrows, ncols, eff_d, cond)

            row_cells = {r: [c for c in range(1, ncols + 1) if (r, c) in grid]
                         for r in range(1, nrows + 1)}
            top_line = all(on(ce(1, c)["top"]) for c in row_cells[1])
            bottom_line = all(on(ce(nrows, c)["bottom"]) for c in row_cells[nrows])
            header_line = all(on(ce(1, c)["bottom"]) for c in row_cells[1])
            no_vert = all(not on(ce(r, c)["left"]) and not on(ce(r, c)["right"])
                          for r, cs in row_cells.items() for c in cs)
            interior = all(not on(ce(r, c)["bottom"])
                           for r in range(2, nrows) for c in row_cells[r])
            is_three = top_line and bottom_line and header_line and no_vert and interior
            if is_three:
                three.append((stem, i, t["rows"], t["cols"], sid))
            three_key = (stem, i)
            three_set.add(three_key) if is_three else None
            w = wps_three(t)
            if w:
                wps_three_set.add(three_key)
            if is_three != w:
                three_disagree.append((stem, i, t["rows"], t["cols"], sid,
                                       "OOXML三线/WPS非三线" if is_three
                                       else "OOXML非三线/WPS三线"))

            # 分布
            for e in EDGES6:
                n = wps_norm(wps_raw(t["edges"], e))
                if n:
                    linestyle_tbl[(e, n[0])] += 1
            for cell in t["cells"]:
                for e in EDGES4:
                    raw = wps_raw(cell.get("edges"), e)
                    n = wps_norm(raw)
                    if not n:
                        continue
                    linestyle_cell[(n[0], raw.get("style"))] += 1
                    if n[0] == "off":
                        off_width[raw.get("width")] += 1
                        # OOXML 该边是 nil/none/未设？
                        od = cell_edges(grid, cell["r"], cell["c"], nrows, ncols, eff_d)
                        if od:
                            off_vs_nil[(od[e], raw.get("width"))] += 1

    print("===== 表级：WPS Table.Borders 6 边 vs 单元格合并模型 =====")
    print(f"  direct 模型（表样式基础⊕直接 tblBorders）: {tbl_direct[0]}/{tbl_direct[1]} "
          f"= {tbl_direct[0] / tbl_direct[1] * 100:.2f}%")
    print(f"  std 模型（再叠 tblStylePr 条件格式）      : {tbl_std[0]}/{tbl_std[1]} "
          f"= {tbl_std[0] / tbl_std[1] * 100:.2f}%")
    for row in tbl_mism:
        print("   ", row)

    print("\n===== 单元：WPS Cell.Borders 4 边 =====")
    print(f"  direct 模型: {cell_direct[0]}/{cell_direct[1]} = "
          f"{cell_direct[0] / cell_direct[1] * 100:.3f}%  标签 {dict(cell_label_d.most_common())}")
    print(f"  std    模型: {cell_std[0]}/{cell_std[1]} = "
          f"{cell_std[0] / cell_std[1] * 100:.3f}%  标签 {dict(cell_label_s.most_common())}")
    print("  std 不一致清单（前 20）：")
    for row in cell_mism_std:
        print("   ", row)

    print("\n===== Rows.Item(1) 与 vMerge 相关性 =====")
    for (has_vm, none), n in sorted(vm_corr.items()):
        print(f"  vMerge={has_vm}  Rows.Item(1)为None={none}: {n} 表")

    print(f"\n===== 真三线表（std 模型：上下线 + 表头下线，无竖线/其它横线）：{len(three)} 个 =====")
    for stem, i, rows, cols, sid in three:
        print(f"  {stem} 表{i} ({rows}x{cols}) style={sid}")

    print(f"\n===== 三线表可判性：OOXML {len(three_set)} 个 vs WPS 判出 {len(wps_three_set)} 个 =====")
    print(f"  一致 {len(three_set & wps_three_set)} / 不一致 {len(three_disagree)}")
    for row in three_disagree:
        print("   ", row)

    print("\n===== WPS 单元格 LineStyle 分布（presence, style）=====")
    for k, n in sorted(linestyle_cell.items(), key=lambda x: -x[1]):
        print(f"  {k}: {n}")
    print("  LineStyle=0 时 LineWidth 分布：", dict(off_width))
    print("  (OOXML有效值, WPS LineWidth) 交叉：", dict(off_vs_nil.most_common(12)))
    print("\n===== WPS 表级各边 presence 分布 =====")
    for k, n in sorted(linestyle_tbl.items()):
        print(f"  {k}: {n}")

    bad_tbl = [x for x in per_table if x[5] != x[6]]
    bad_cell = [x for x in per_table if x[7] != x[8]]
    print(f"\n===== 逐表一致率（{len(per_table)} 表）=====")
    print(f"  表级 100% 的 {len(per_table) - len(bad_tbl)} 表；有差异的 {len(bad_tbl)} 表：")
    for stem, i, rows, cols, sid, ok, tot, cok, ctot in bad_tbl:
        print(f"    {stem[:40]:<40} 表{i} ({rows}x{cols}) 表级 {ok}/{tot} 单元 {cok}/{ctot}")
    print(f"  单元 100% 的 {len(per_table) - len(bad_cell)} 表；有差异的 {len(bad_cell)} 表（"
          f"差异均为“均无宽度表示不同”或“WPS 合并位给 None”）：")
    for stem, i, rows, cols, sid, ok, tot, cok, ctot in bad_cell:
        print(f"    {stem[:40]:<40} 表{i} ({rows}x{cols}) 表级 {ok}/{tot} 单元 {cok}/{ctot}")
    print("\n  全部逐表明细：")
    for stem, i, rows, cols, sid, ok, tot, cok, ctot in per_table:
        print(f"    {stem[:40]:<40} 表{i:<3} ({rows}x{cols}) 表级 {ok}/{tot} 单元 {cok}/{ctot}")


if __name__ == "__main__":
    main()
