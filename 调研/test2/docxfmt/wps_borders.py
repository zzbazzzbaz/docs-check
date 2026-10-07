"""表格边框在 WPS 里的真值（容器内跑）。

用法（容器内）：
    python3 /opt/wps_borders.py --outdir /out --list /out/paths_bd.txt

输出 <outdir>/<stem>.wpsborders.json。口径：
  * 每表取 Table.Borders 的 6 条边（top/left/bottom/right/insideH/insideV）：
    style=LineStyle（wdLineStyle），width=LineWidth（wdLineWidth，1/8 pt）。
  * 单元格只采前 2 行 × 前 3 列；Cell.Borders 只认 1..4（top/left/bottom/right），
    inside_h/inside_v 给 null。
  * 取不到一律 null，不抛。
  * WPS 只数顶层表格，与自研 Tables.Count 口径一致。

实测约定：
  * Table.Borders / Cell.Borders 报的是**有效值**（含表样式 tblPr/tblBorders，
    且单元格 tcBorders 能顶掉表级），单元格间不一致时 LineStyle/LineWidth = 9999999（wdUndefined）。
  * **表样式的 tblStylePr 条件格式（如 firstRow 表头下框线）WPS 不认**，只认 tblPr/tblBorders。
  * LineStyle=0 时 LineWidth：显式 none/nil → 0；从未设过 → 2（可见性仍为 False）。
  * Row.Borders / Column.Borders 存在，但语义不稳（同一行内单元格不一致时也给 9999999）。
  * Table.Style 返回的是文档默认表样式名（实测都是"网格型"），不是本表实际引用，别用。
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

EDGES = (("top", 1), ("left", 2), ("bottom", 3), ("right", 4),
         ("inside_h", 5), ("inside_v", 6))
UNDEFINED = 9999999
SAMPLE_ROWS = 2
SAMPLE_COLS = 3

FAILED: dict[str, int] = {}


def unwrap(v):
    if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], int):
        return v[1]
    return v


def g(obj, name, default=None):
    try:
        return unwrap(getattr(obj, name))
    except Exception:
        FAILED[name] = FAILED.get(name, 0) + 1
        return default


def count_of(obj) -> int:
    try:
        return int(g(obj, "Count") or 0)
    except (TypeError, ValueError):
        return 0


def edge_map(borders, keys=EDGES) -> dict:
    out = {}
    for name, k in keys:
        try:
            bd = unwrap(borders.Item(k))
            out[name] = {"style": g(bd, "LineStyle"), "width": g(bd, "LineWidth")}
        except Exception:
            FAILED["Borders.Item"] = FAILED.get("Borders.Item", 0) + 1
            out[name] = {"style": None, "width": None}
    return out


def cell_edges(cell) -> dict:
    b = g(cell, "Borders")
    if b is None:
        return {name: None for name, _ in EDGES}
    out = edge_map(b, EDGES[:4])
    out["inside_h"] = None
    out["inside_v"] = None
    return out


def first_edge_map(table, coll_name: str) -> dict | None:
    try:
        coll = unwrap(getattr(table, coll_name))
        item = unwrap(coll.Item(1))
        if item is None:
            FAILED[f"{coll_name}.Item1None"] = FAILED.get(f"{coll_name}.Item1None", 0) + 1
            return None
        b = g(item, "Borders")
        return edge_map(b) if b is not None else None
    except Exception:
        FAILED[f"{coll_name}.Borders"] = FAILED.get(f"{coll_name}.Borders", 0) + 1
        return None


def dump_table(t, i: int) -> dict:
    nrows = count_of(g(t, "Rows"))
    ncols = count_of(g(t, "Columns"))
    tb = g(t, "Borders")
    sr = min(SAMPLE_ROWS, nrows)
    sc = min(SAMPLE_COLS, ncols)
    cells = []
    for r in range(1, sr + 1):
        for c in range(1, sc + 1):
            try:
                cell = unwrap(t.Cell(r, c))
            except Exception:
                FAILED["Table.Cell"] = FAILED.get("Table.Cell", 0) + 1
                cell = None
            cells.append({"r": r, "c": c,
                          "edges": cell_edges(cell) if cell is not None else None})
    return {
        "i": i,
        "rows": nrows,
        "cols": ncols,
        "enable": g(tb, "Enable") if tb is not None else None,
        "style": g(t, "Style") or None,
        "edges": edge_map(tb) if tb is not None else {},
        "row1_edges": first_edge_map(t, "Rows"),
        "col1_edges": first_edge_map(t, "Columns"),
        "sample_rows": sr,
        "sample_cols": sc,
        "cells": cells,
    }


def dump_one(app, path: Path, outdir: Path) -> dict:
    _, doc = app.Documents.Open(str(path))
    tables = g(doc, "Tables")
    n = count_of(tables)
    rows = []
    for i in range(1, n + 1):
        try:
            t = unwrap(tables.Item(i))
        except Exception:
            FAILED["Tables.Item"] = FAILED.get("Tables.Item", 0) + 1
            continue
        if t is None:
            FAILED["Tables.ItemNone"] = FAILED.get("Tables.ItemNone", 0) + 1
            continue
        try:
            rows.append(dump_table(t, i))
        except Exception:
            FAILED["dump_table"] = FAILED.get("dump_table", 0) + 1
            traceback.print_exc()
    out = {"path": str(path), "tool": "wps",
           "counts": {"tables": n}, "tables": rows}
    (outdir / f"{path.stem}.wpsborders.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {path.stem}: 表 {len(rows)}/{n}")
    try:
        doc.Close(0)
    except Exception:
        pass
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--list", dest="listfile", help="每行一个 docx 路径（文件名带空格时用）")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    targets = list(args.paths)
    if args.listfile:
        targets += [
            ln.strip()
            for ln in Path(args.listfile).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    from pywpsrpc.rpcwpsapi import createWpsRpcInstance

    _, rpc = createWpsRpcInstance()
    hr, app = rpc.getWpsApplication()
    print(f"WPS 就绪 (hr={hr})")
    try:
        app.Visible = False
    except Exception:
        pass

    ok = 0
    for arg in targets:
        p = Path(arg)
        if not p.exists():
            print(f"  !! 跳过（不存在）{p}", file=sys.stderr)
            continue
        try:
            dump_one(app, p, outdir)
            ok += 1
        except Exception:
            print(f"  !! {p.name} 失败", file=sys.stderr)
            traceback.print_exc()
    print(f"\n完成 {ok}/{len(targets)}")
    print("== 取不到的属性 ==")
    for k, v in sorted(FAILED.items(), key=lambda x: -x[1]) or [("（无）", 0)]:
        print(f"  {k}: {v}")
    try:
        app.Quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
