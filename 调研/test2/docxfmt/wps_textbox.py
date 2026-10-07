"""文本框（`w:txbxContent`）内容在 WPS 里的真值（容器内跑）。

用法（容器内）：
    python3 /opt/wps_textbox.py --outdir /out --list /out/paths_tb.txt

输出 <outdir>/<stem>.wpstextbox.json。覆盖 GLB-28（禁用自动编号）要查的「文本框」那一半。

实测约定：
  * 只要是文本框，**不管 VML(`v:textbox`) 还是 DrawingML(`wps:txbx`)、不管内联还是浮动，
    都落在 `doc.Shapes`**；`InlineShapes` 没有 `.TextFrame` 属性，取不到内容。
  * `Shape.TextFrame.HasText` 为真（-1）即代表有文本框（空文本框也真，`TextRange.Text == "\\r"`）；
    没有文本框的图形（矩形/连接符/FreeForm）HasText 为 0，对它取 `TextRange` 会报 0x80000008。
  * `Shape.Type == 6` 是组合（GroupItems）：组自身 `TextRange` 报 0x80000008，要下钻
    `GroupItems.Item(k)` 递归；组内文本框（Type=17）自身的 `TextFrame`/`TextRange` 正常。
  * `anchor_para` 用 `Shape.Anchor.Start` 落在哪一段（与 wps_fields 同一套逐段 Range 口径）。
  * 逐段字体/字号沿用 wps.py 的 scan_chars/_sample（含内容控件首段 Characters 偏一位的核对）。
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
import traceback
from pathlib import Path

MSO_GROUP = 6

FAILED: dict[str, int] = {}
UNMAPPED = 0


def safe_text(raw) -> tuple[str, bool]:
    """取最长可读前缀（星形平面字符会让 pywpsrpc 的 str 坏掉）。"""
    try:
        for i, c in enumerate(raw):
            if c == "\x00" or 0xD800 <= ord(c) <= 0xDFFF:
                return raw[:i], True
        return raw, False
    except Exception:
        pass
    parts = []
    for i in range(len(raw)):
        try:
            c = raw[i]
        except Exception:
            break
        if c == "\x00" or 0xD800 <= ord(c) <= 0xDFFF:
            return "".join(parts), True
        parts.append(c)
    return "".join(parts), True


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


def deep(obj, *names, default=None):
    for n in names:
        try:
            obj = unwrap(getattr(obj, n))
        except Exception:
            FAILED[n] = FAILED.get(n, 0) + 1
            return default
        if obj is None:
            return default
    return obj


def is_cjk_char(c: str) -> bool:
    o = ord(c)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
            or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF) and c.strip() != ""


def clean_text(s: str) -> str:
    return re.sub(r"[\r\a\x07\x0c]", "", s)


def _one_char_font(font) -> dict:
    return {"font": g(font, "Name") or None, "ea": g(font, "NameFarEast") or None,
            "size": g(font, "Size")}


def _sample(chars, text: str, i: int):
    """取文本第 i 位（0-based）那个字符的字体；与文本核对，含内容控件首段偏一位的兜底。"""
    wanted = text[i]
    fallback = None
    for k in (i + 1, i + 2, i):
        if k < 1:
            continue
        try:
            ch = unwrap(chars.Item(k))
            rec = _one_char_font(ch.Font)
            rec["char"] = ch.Text
        except Exception:
            FAILED["Characters.Item"] = FAILED.get("Characters.Item", 0) + 1
            continue
        if fallback is None:
            fallback = rec
        if rec["char"] == wanted:
            return rec
    return fallback


def scan_chars(para, text: str):
    def first(pred):
        try:
            for i, c in enumerate(text):
                if pred(c):
                    return i
        except Exception:
            pass
        return None

    i_w = first(lambda c: c.isascii() and c.isalnum())
    i_e = first(is_cjk_char)
    if i_w is None and i_e is None:
        return None, None
    try:
        chars = para.Range.Characters
    except Exception:
        FAILED["Range.Characters"] = FAILED.get("Range.Characters", 0) + 1
        return None, None
    return (
        None if i_w is None else _sample(chars, text, i_w),
        None if i_e is None else _sample(chars, text, i_e),
    )


def para_ranges(doc) -> tuple[list[int], list[int]]:
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


def count_of(doc, name) -> int:
    coll = g(doc, name)
    try:
        return int(g(coll, "Count") or 0) if coll is not None else 0
    except (TypeError, ValueError):
        return 0


def locate(starts: list[int], ends: list[int], pos) -> int | None:
    if pos is None or not starts:
        return None
    j = bisect.bisect_right(starts, pos) - 1
    if j < 0 or ends[j] < 0 or pos > ends[j]:
        return None
    return j + 1


def scan_fields(tr) -> list:
    fs = g(tr, "Fields")
    if fs is None:
        return []
    out = []
    for i in range(1, int(g(fs, "Count") or 0) + 1):
        try:
            f = unwrap(fs.Item(i))
        except Exception:
            FAILED["Fields.Item"] = FAILED.get("Fields.Item", 0) + 1
            continue
        raw = g(g(f, "Code"), "Text")
        code = None
        if raw is not None:
            toks = str(raw).split()
            code = toks[0].upper() if toks else None
        out.append({"code": code, "code_text": None if raw is None else str(raw),
                    "type": g(f, "Type")})
    return out


def scan_paragraphs(tr) -> list:
    ps = g(tr, "Paragraphs")
    if ps is None:
        return []
    rows = []
    for i in range(1, int(g(ps, "Count") or 0) + 1):
        try:
            para = unwrap(ps.Item(i))
        except Exception:
            FAILED["Paragraphs.Item"] = FAILED.get("Paragraphs.Item", 0) + 1
            continue
        raw, _ = safe_text(str(deep(para, "Range", "Text") or ""))
        west, east = scan_chars(para, raw)
        size = (west or {}).get("size")
        if size is None:
            size = (east or {}).get("size")
        rows.append({
            "text": clean_text(raw),
            "font_ea": ((east or {}).get("ea") or (east or {}).get("font")),
            "font_ascii": (west or {}).get("font"),
            "size": size,
            "align": g(g(para, "Format"), "Alignment"),
            "list_type": deep(para, "Range", "ListFormat", "ListType"),
            "list_string": deep(para, "Range", "ListFormat", "ListString"),
        })
    return rows


def box_of(sh, kind: str, starts, ends) -> dict | None:
    tf = g(sh, "TextFrame")
    if tf is None or not g(tf, "HasText"):
        return None
    tr = g(tf, "TextRange")
    if tr is None:
        return None
    pos = g(g(sh, "Anchor"), "Start")
    raw, _ = safe_text(str(g(tr, "Text") or ""))
    return {
        "kind": kind,
        "shape_type": g(sh, "Type"),
        "anchor_para": locate(starts, ends, pos),
        "text": clean_text(raw),
        "fields": scan_fields(tr),
        "paragraphs": scan_paragraphs(tr),
    }


def walk_shape(sh, kind: str, boxes: list, starts, ends) -> None:
    if g(sh, "Type") == MSO_GROUP:
        items = g(sh, "GroupItems")
        if items is not None:
            for k in range(1, int(g(items, "Count") or 0) + 1):
                try:
                    sub = unwrap(items.Item(k))
                except Exception:
                    FAILED["GroupItems.Item"] = FAILED.get("GroupItems.Item", 0) + 1
                    continue
                walk_shape(sub, kind, boxes, starts, ends)
        return
    box = box_of(sh, kind, starts, ends)
    if box is not None:
        boxes.append(box)


def dump_one(app, path: Path, outdir: Path) -> dict:
    global UNMAPPED
    _, doc = app.Documents.Open(str(path))
    starts, ends = para_ranges(doc)

    boxes: list = []
    shapes = g(doc, "Shapes")
    if shapes is not None:
        for i in range(1, int(g(shapes, "Count") or 0) + 1):
            try:
                walk_shape(unwrap(shapes.Item(i)), "shape", boxes, starts, ends)
            except Exception:
                FAILED["Shapes.Item"] = FAILED.get("Shapes.Item", 0) + 1

    inl = g(doc, "InlineShapes")
    if inl is not None:
        for i in range(1, int(g(inl, "Count") or 0) + 1):
            try:
                ish = unwrap(inl.Item(i))
            except Exception:
                continue
            try:
                getattr(ish, "TextFrame")
            except AttributeError:
                continue  # InlineShape 没有 TextFrame，内容取不到
            box = box_of(ish, "inline_shape", starts, ends)
            if box is not None:
                boxes.append(box)

    for k, b in enumerate(boxes, 1):
        b["i"] = k
        if b["anchor_para"] is None:
            UNMAPPED += 1

    ordered = ["i", "kind", "shape_type", "anchor_para", "text", "fields", "paragraphs"]
    boxes = [{k: b[k] for k in ordered} for b in boxes]

    counts = {
        "boxes": len(boxes),
        "boxes_with_text": sum(1 for b in boxes if b["text"].strip()),
        "boxes_with_fields": sum(1 for b in boxes if b["fields"]),
    }
    out = {"path": str(path), "tool": "wps", "counts": counts, "boxes": boxes}
    (outdir / f"{path.stem}.wpstextbox.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {path.stem}: 框{counts['boxes']} 有字{counts['boxes_with_text']} "
          f"有域{counts['boxes_with_fields']}")
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
    print(f"anchor_para 映射不到: {UNMAPPED}")
    print("== 取不到的属性 ==")
    for k, v in sorted(FAILED.items(), key=lambda x: -x[1]) or [("（无）", 0)]:
        print(f"  {k}: {v}")
    try:
        app.Quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
