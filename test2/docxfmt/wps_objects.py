"""图片 / 图形 / 公式对象在 WPS 里的真值，逐个归属到段落（容器内跑）。

用法（容器内）：
    python3 /opt/wps_objects.py --outdir /out --list /out/paths_obj.txt

输出 <outdir>/<stem>.wpsobjects.json。归属口径：对象起点（InlineShapes 用
Range.Start、Shapes 用 Anchor.Start、OMaths 用 Range.Start）落在哪一段的
[Range.Start, Range.End) 里就归给它。WPS 的 Paragraphs 含表格行末标记，段落序与 OOXML 不同。

实测约定：
  * InlineShape 没有 .Anchor，只有 .Range；Shape 用 .Anchor 才有 Range
  * InlineShape.Type：1=OLE 对象，3=图片
  * doc/Paragraph.Range.OMaths.Count 可用，doc.OMaths.Count 与 OOXML 的 m:oMath 数一致
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
import traceback
from pathlib import Path

FAILED: dict[str, int] = {}
UNMAPPED: dict[str, int] = {"inline_shapes": 0, "shapes": 0, "omaths": 0}


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


def count_of(doc, name) -> int:
    coll = g(doc, name)
    try:
        return int(g(coll, "Count") or 0) if coll is not None else 0
    except (TypeError, ValueError):
        return 0


def para_ranges(doc) -> tuple[list[int], list[int]]:
    """逐段取 [Range.Start, Range.End)。取不到的段记 (-1, -1) 仍占位，保持下标一致。"""
    paras = g(doc, "Paragraphs")
    n = count_of(doc, "Paragraphs")
    starts, ends = [], []
    for i in range(1, n + 1):
        try:
            r = unwrap(paras.Item(i)).Range
            starts.append(int(unwrap(r.Start)))
            ends.append(int(unwrap(r.End)))
        except Exception:
            FAILED["Paragraphs.Item.Range"] = FAILED.get("Paragraphs.Item.Range", 0) + 1
            starts.append(-1)
            ends.append(-1)
    return starts, ends


def locate(starts: list[int], ends: list[int], pos) -> int | None:
    """pos 落在哪一段（0-based）；映射不到给 None。"""
    if pos is None or not starts:
        return None
    j = bisect.bisect_right(starts, pos) - 1
    if j < 0 or ends[j] < 0 or pos > ends[j]:
        return None
    return j


def scan(doc, coll_name: str, pos_of, type_of=None) -> list[tuple]:
    """→ [(type|None, pos|None)]。Item 取不到就跳过，起点取不到记 pos=None。"""
    coll = g(doc, coll_name)
    if coll is None:
        return []
    rows = []
    for i in range(1, count_of(doc, coll_name) + 1):
        try:
            obj = unwrap(coll.Item(i))
        except Exception:
            FAILED[f"{coll_name}.Item"] = FAILED.get(f"{coll_name}.Item", 0) + 1
            continue
        typ = type_of(obj) if type_of else None
        try:
            pos = pos_of(obj)
        except Exception:
            FAILED[f"{coll_name}.Start"] = FAILED.get(f"{coll_name}.Start", 0) + 1
            pos = None
        rows.append((typ, pos))
    return rows


def dump_one(app, path: Path, outdir: Path) -> dict:
    _, doc = app.Documents.Open(str(path))

    starts, ends = para_ranges(doc)
    per = [{"i": k + 1, "inline_shapes": 0, "shapes": 0, "omaths": 0}
           for k in range(len(starts))]

    def assign(rows, key: str) -> dict[str, int]:
        by_type: dict[str, int] = {}
        for typ, pos in rows:
            if typ is not None:
                by_type[str(typ)] = by_type.get(str(typ), 0) + 1
            j = locate(starts, ends, pos)
            if j is None:
                UNMAPPED[key] += 1
            else:
                per[j][key] += 1
        return by_type

    inline_types = assign(
        scan(doc, "InlineShapes", lambda o: int(unwrap(o.Range.Start)), lambda o: g(o, "Type")),
        "inline_shapes",
    )
    shape_types = assign(
        scan(doc, "Shapes", lambda o: int(unwrap(o.Anchor.Start)), lambda o: g(o, "Type")),
        "shapes",
    )
    assign(scan(doc, "OMaths", lambda o: int(unwrap(o.Range.Start))), "omaths")

    out = {
        "path": str(path),
        "tool": "wps",
        "counts": {
            "paragraphs": count_of(doc, "Paragraphs"),
            "inline_shapes": count_of(doc, "InlineShapes"),
            "inline_by_type": inline_types,
            "shapes": count_of(doc, "Shapes"),
            "shapes_by_type": shape_types,
            "tables": count_of(doc, "Tables"),
            "omaths": count_of(doc, "OMaths"),
            "fields": count_of(doc, "Fields"),
        },
        "paragraphs": per,
    }
    (outdir / f"{path.stem}.wpsobjects.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    c = out["counts"]
    print(f"  {path.stem}: 段{c['paragraphs']} 内嵌{c['inline_shapes']}{c['inline_by_type']} "
          f"浮动{c['shapes']}{c['shapes_by_type']} 公式{c['omaths']} 表{c['tables']} 域{c['fields']}")
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
    print(f"映射不到的：{UNMAPPED}")
    print("== 取不到的属性 ==")
    for k, v in sorted(FAILED.items(), key=lambda x: -x[1]) or [("（无）", 0)]:
        print(f"  {k}: {v}")
    try:
        app.Quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
