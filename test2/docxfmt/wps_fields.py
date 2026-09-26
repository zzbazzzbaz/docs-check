"""域（field）与 TOC 域跨度的 WPS 真值（容器内跑）。

用法（容器内）：
    python3 /opt/wps_fields.py --outdir /out --list /out/paths_fld.txt

输出 <outdir>/<stem>.wpsfields.json。

实测约定：
  * Field 对象**没有** .Range（AttributeError），只有 .Code 与 .Result 两个 Range；
    所以「域的跨度」= Code.Start 起、Result.End 止。Code 就是 w:instrText 那段。
  * 段落 Range 相邻共享端点（p_j.End == p_{j+1}.Start），所以末段落落点要用 End-1。
  * doc.Fields 会把 TOC 结果里嵌套的 PAGEREF/HYPERLINK 一并列出，TOC 在前、
    嵌套域按文档顺序跟在后面。
  * doc.Fields **只给正文**，页眉页脚里的域要单独遍历
    Sections.Item(k).Headers/Footers.Item(j).Range.Fields 才取得到。
  * 自研口径「文本框不下钻」，w:txbxContent 里的域两边都不算。
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
import traceback
from pathlib import Path

FAILED: dict[str, int] = {}
UNMAPPED = 0


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
    """pos 落在哪一段（1 起的段落号）；映射不到给 None。"""
    if pos is None or not starts:
        return None
    j = bisect.bisect_right(starts, pos) - 1
    if j < 0 or ends[j] < 0 or pos > ends[j]:
        return None
    return j + 1


def bounds_of(f, code_range) -> tuple[int | None, int | None]:
    """域跨度：Code.Start 起、Result.End 止。取不到的一头给 None。"""
    start = end = None
    if code_range is not None:
        start = g(code_range, "Start")
        end = g(code_range, "End")
    res = g(f, "Result")
    if res is not None:
        if start is None:
            start = g(res, "Start")
        end = g(res, "End")
    return start, end


def code_of(f, code_range) -> tuple[str | None, str | None]:
    """→ (域代码首词大写, Field.Code.Text 原样去首尾空白)。"""
    if code_range is None:
        return None, None
    raw = g(code_range, "Text")
    if raw is None:
        return None, None
    text = str(raw).strip()
    toks = text.split()
    return (toks[0].upper() if toks else None), text


def dump_one(app, path: Path, outdir: Path) -> dict:
    global UNMAPPED
    _, doc = app.Documents.Open(str(path))
    starts, ends = para_ranges(doc)

    fields_coll = g(doc, "Fields")
    n = count_of(doc, "Fields")
    rows = []
    for i in range(1, n + 1):
        try:
            f = unwrap(fields_coll.Item(i))
        except Exception:
            FAILED["Fields.Item"] = FAILED.get("Fields.Item", 0) + 1
            continue
        code_range = g(f, "Code")
        code, code_text = code_of(f, code_range)
        start, end = bounds_of(f, code_range)
        para = locate(starts, ends, start)
        if end is not None:
            last = max(start if start is not None else end, end - 1)
        else:
            last = start
        end_para = locate(starts, ends, last)
        if para is None or end_para is None:
            UNMAPPED += 1
        rows.append({"i": i, "type": g(f, "Type"), "code": code,
                     "code_text": code_text, "para": para, "end_para": end_para})

    by_code: dict[str, int] = {}
    for r in rows:
        key = r["code"] or "(空)"
        by_code[key] = by_code.get(key, 0) + 1

    out = {
        "path": str(path),
        "tool": "wps",
        "counts": {"fields": n, "by_code": by_code},
        "fields": rows,
        "toc_spans": [{"code": "TOC", "para": r["para"], "end_para": r["end_para"]}
                      for r in rows if r["code"] == "TOC"],
    }
    (outdir / f"{path.stem}.wpsfields.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {path.stem}: 域{n} {by_code} TOC跨度{out['toc_spans']}")
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
    print(f"段落映射不到: {UNMAPPED}")
    print("== 取不到的属性 ==")
    for k, v in sorted(FAILED.items(), key=lambda x: -x[1]) or [("（无）", 0)]:
        print(f"  {k}: {v}")
    try:
        app.Quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
