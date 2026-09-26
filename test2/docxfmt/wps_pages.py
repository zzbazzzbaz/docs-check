"""页面设置 / 分节 / 页眉页脚的 WPS 真值（容器内跑）。

用法（容器内）：
    python3 /opt/wps_pages.py --outdir /out --list /out/paths.txt

输出 <outdir>/<stem>.wpspages.json，单位 pt。段落取字体沿用 wps.py 的 _sample：
WPS 在内容控件首段的 Characters 会偏一位，要拿返回字符和文本核对。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

HF_TYPE = {1: "default", 2: "first", 3: "even"}
ORIENT = {0: "portrait", 1: "landscape"}
UNDEFINED = 9999999
FAILED: dict[str, int] = {}


def safe_text(raw) -> tuple[str, bool]:
    """取最长可读前缀。pywpsrpc 的 str 可能按 UTF-16 单位数虚长，读坏位会 SystemError。"""
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


def tri(v) -> bool | None:
    if v is None or v == UNDEFINED:
        return None
    return bool(v)


def num(v):
    if v is None or v == UNDEFINED:
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def enum(v):
    return None if v is None or v == UNDEFINED else v


def is_cjk_char(c: str) -> bool:
    o = ord(c)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
            or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF) and c.strip() != ""


def _one_char_font(font) -> dict:
    return {"font": g(font, "Name") or None, "ea": g(font, "NameFarEast") or None,
            "size": num(g(font, "Size"))}


def _sample(chars, text: str, i: int):
    """取文本第 i 位的字符字体；sdt 首段 Characters 偏一位，靠返回字符核对。"""
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
    """第一个 ASCII 字母数字与第一个中文字的字体。索引用原始文本算。"""
    def first(pred):
        for i, c in enumerate(text):
            if pred(c):
                return i
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
    return (None if i_w is None else _sample(chars, text, i_w),
            None if i_e is None else _sample(chars, text, i_e))


def page_setup(ps) -> dict:
    return {
        "w_pt": num(g(ps, "PageWidth")),
        "h_pt": num(g(ps, "PageHeight")),
        "orientation": ORIENT.get(g(ps, "Orientation")),
        "top_pt": num(g(ps, "TopMargin")),
        "bottom_pt": num(g(ps, "BottomMargin")),
        "left_pt": num(g(ps, "LeftMargin")),
        "right_pt": num(g(ps, "RightMargin")),
        "header_pt": num(g(ps, "HeaderDistance")),
        "footer_pt": num(g(ps, "FooterDistance")),
        "paper_size": enum(g(ps, "PaperSize")),
    }


def page_number_format(section):
    """w:pgNumType/@fmt 的 WPS 侧取值（wdPageNumberStyle）。按节取，页脚优先。"""
    for attr in ("Footers", "Headers"):
        try:
            hf = unwrap(getattr(section, attr).Item(1))
            return enum(unwrap(hf.PageNumbers.NumberStyle))
        except Exception:
            FAILED["PageNumbers.NumberStyle"] = FAILED.get("PageNumbers.NumberStyle", 0) + 1
    return None


def dump_hf(collection, j: int) -> dict:
    rec = {"type": HF_TYPE[j], "text": None, "paragraphs": [],
           "link_to_previous": None, "page_fields": None, "field_types": []}
    try:
        hf = unwrap(collection.Item(j))
        text, _ = safe_text(str(hf.Range.Text or ""))
        rec["text"] = text
        count = int(unwrap(hf.Range.Paragraphs.Count) or 0)
    except Exception:
        FAILED["HeaderFooter.Range"] = FAILED.get("HeaderFooter.Range", 0) + 1
        return rec

    # LinkToPrevious=真 → 本节没有自己该类型的页眉/页脚，沿用上一节（第一节无上一节，恒为假）
    rec["link_to_previous"] = tri(g(hf, "LinkToPrevious"))
    # 页码域必须靠 Fields 判（含 PAGE 域的文本会随重新分页而变，不可靠）
    try:
        fields = hf.Range.Fields
        n = int(unwrap(fields.Count) or 0)
        rec["field_types"] = [enum(g(unwrap(fields.Item(i)), "Type")) for i in range(1, n + 1)]
        rec["page_fields"] = sum(1 for t in rec["field_types"] if t == 33)   # wdFieldPage
    except Exception:
        FAILED["HeaderFooter.Fields"] = FAILED.get("HeaderFooter.Fields", 0) + 1

    for pi in range(1, count + 1):
        try:
            para = unwrap(hf.Range.Paragraphs.Item(pi))
            raw, _ = safe_text(str(para.Range.Text or ""))
        except Exception:
            FAILED["HeaderFooter.Paragraphs.Item"] = \
                FAILED.get("HeaderFooter.Paragraphs.Item", 0) + 1
            continue
        clean = re.sub(r"[\r\a\x07\x0c]", "", raw)
        if not clean.strip():
            continue
        west, east = scan_chars(para, raw)
        rec["paragraphs"].append({
            "text": clean,
            "font_ea": east["ea"] if east else None,
            "font_ascii": west["font"] if west else None,
            "size": (east or west or {}).get("size"),
            "align": enum(g(para.Format, "Alignment")),
        })
    return rec


def dump_one(app, path: Path, outdir: Path) -> int:
    _, doc = app.Documents.Open(str(path))
    sections = g(doc, "Sections")
    count = int(g(sections, "Count") or 0)
    rows = []
    for k in range(1, count + 1):
        sec = unwrap(sections.Item(k))
        ps = sec.PageSetup
        rows.append({
            "index": k,
            "page": page_setup(ps),
            "page_number_format": page_number_format(sec),
            "different_first_page": tri(g(ps, "DifferentFirstPageHeaderFooter")),
            "odd_and_even_pages": tri(g(ps, "OddAndEvenPagesHeaderFooter")),
            "headers": [dump_hf(sec.Headers, j) for j in (1, 2, 3)],
            "footers": [dump_hf(sec.Footers, j) for j in (1, 2, 3)],
        })
    (outdir / f"{path.stem}.wpspages.json").write_text(
        json.dumps({"path": str(path), "tool": "wps", "sections": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {path.stem}: {len(rows)} 节")
    try:
        doc.Close(0)
    except Exception:
        pass
    return len(rows)


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
