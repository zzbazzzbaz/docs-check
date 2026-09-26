"""WPS 真值侧：在 headless WPS 容器里跑，让 WPS 自己算出每段最终生效的格式。

用法（容器内）：
    python3 /opt/wps.py --outdir /out /in/*.docx

pywpsrpc 的实测约定：
  * 方法返回 (hr, value)，属性直接返回值 → Item() 之类要先解包
  * Documents.Open 只吃位置参数
  * 段落格式在 Paragraph.Format（不是 ParagraphFormat）
  * WPS 把中文字体报成英文名（宋体 → SimSun）。这里保持原样输出，归一交给 compare.py
  * WPS 报的 Paragraphs 含表格行末标记，比自研多几段
  * pywpsrpc 的 Range.Text 遇到星形平面字符（U+10000 以上，如数学斜体 𝐵）会坏：
    它按 UTF-16 单位数建 str，真实字符数更少，多出来的位置是未初始化内存，
    一读到就 SystemError。见 safe_text()
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

ALIGN = {0: "left", 1: "center", 2: "right", 3: "both", 4: "distribute"}
OUTLINE_BODY = 10
RULE_SINGLE, RULE_1P5, RULE_DOUBLE, RULE_ATLEAST, RULE_EXACT, RULE_MULTIPLE = 0, 1, 2, 3, 4, 5

FAILED: dict[str, int] = {}
TRUNCATED = 0
FORMULA_NO = re.compile(r"\((\d+)\s*-\s*(\d+)\)")


def formula_no(para, text: str):
    """公式编号 `(n-m)` 那个字符的字体/字号。

    采样位置与自研一致（第一个 `(` 之后的那位），因为公式段落里公式本体在编号之前，
    按「第一个 ASCII run」采样会采错位置。
    """
    m = FORMULA_NO.search(text)
    if m is None:
        return None
    try:
        chars = para.Range.Characters
    except Exception:
        FAILED["Range.Characters"] = FAILED.get("Range.Characters", 0) + 1
        return None
    rec = _sample(chars, text, m.start() + 1)
    if rec is None:
        return None
    return {"no": f"{m.group(1)}-{m.group(2)}", "font": rec.get("font"),
            "ea": rec.get("ea"), "size": rec.get("size")}


def safe_text(raw) -> tuple[str, bool]:
    """取最长可读前缀。返回 (文本, 是否被截断)。

    pywpsrpc 返回的 str 可能是坏的：len() 是 UTF-16 单位数而非字符数，
    超出真实字符数的位置是未初始化内存。读坏位置会抛 SystemError。

    快路径正常走一遍；一旦抛异常或撞到 NUL / 孤立代理对，就退化成逐索引取，
    取到坏位为止。前缀内容是真的（实测正是完整文本），只是无法保证没被截断。
    """
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


def normalize_line(rule, spacing):
    """→ (类型, 值)；auto 的值是倍数，其余是磅。"""
    if rule in (RULE_SINGLE, RULE_1P5, RULE_DOUBLE, RULE_MULTIPLE):
        mult = {RULE_SINGLE: 1.0, RULE_1P5: 1.5, RULE_DOUBLE: 2.0}.get(rule)
        if mult is None:
            mult = (spacing or 0) / 12.0
        return "auto", round(mult, 2)
    if rule == RULE_ATLEAST:
        return "atLeast", round(spacing or 0, 1)
    if rule == RULE_EXACT:
        return "exact", round(spacing or 0, 1)
    return None, None


def _one_char_font(font) -> dict:
    """原始值输出：取不到给 None，「值是 0/False」和「取不到」必须能分开。"""
    return {"font": g(font, "Name") or None, "ea": g(font, "NameFarEast") or None,
            "size": g(font, "Size"),
            "bold": g(font, "Bold"), "italic": g(font, "Italic"),
            "underline": g(font, "Underline"),
            "sup": g(font, "Superscript"), "sub": g(font, "Subscript")}


def _sample(chars, text: str, i: int):
    """取文本第 i 位（0-based）那个字符的字体。

    WPS 在 sdt（内容控件）**首段**的 Characters 集合里多一个前导元素，
    直接 Item(i+1) 会取到隔壁字符（实测：目录首段偏一位）。
    所以拿到的字符要和文本对得上才认，对不上就试相邻下标；都不对就退回原样。
    """
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
    """取「第一个 ASCII 字母/数字」与「第一个中文字」的字体。

    按索引直接取，不逐字符遍历（模拟环境下会慢到不可用）。
    索引必须用**原始文本**算——Characters 按原始文本计数，含 \\x0c 与 \\r。
    """
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


def dump_one(app, path: Path, outdir: Path) -> int:
    global TRUNCATED
    _, doc = app.Documents.Open(str(path))
    rows = []
    paras = g(doc, "Paragraphs")
    cnt = int(g(paras, "Count")) if paras is not None else 0
    for i in range(1, cnt + 1):
        try:
            para = unwrap(doc.Paragraphs.Item(i))
            text, truncated = safe_text(str(para.Range.Text or ""))
        except Exception:
            FAILED["Paragraphs.Item"] = FAILED.get("Paragraphs.Item", 0) + 1
            continue
        if truncated:
            TRUNCATED += 1
        fmt = getattr(para, "Format", None)
        rule = g(fmt, "LineSpacingRule")
        kind, val = normalize_line(rule, g(fmt, "LineSpacing"))
        west, east = scan_chars(para, text)
        rows.append({
            "i": i,
            "text": re.sub(r"[\r\a\x07\x0c]", "", text),
            # 文本口径的空段落：与自研 text_empty 同义（\x01 内嵌对象占位符不算文字）
            "text_empty": re.sub(r"[\r\a\x07\x0c\v\n\x01\x02\x05\x0e\x13\x14\x15]", "", text) == "",
            "text_truncated": truncated,
            "align": ALIGN.get(g(fmt, "Alignment")),
            "outline": (None if g(para, "OutlineLevel") in (None, OUTLINE_BODY)
                        else g(para, "OutlineLevel") - 1),
            "first_indent": g(fmt, "FirstLineIndent"),
            "first_char_unit": g(fmt, "CharacterUnitFirstLineIndent"),
            "left_indent": g(fmt, "LeftIndent"),
            "right_indent": g(fmt, "RightIndent"),
            "space_before": g(fmt, "SpaceBefore"),
            "space_after": g(fmt, "SpaceAfter"),
            "line_rule": kind,
            "line": val,
            "page_break_before": deep(fmt, "PageBreakBefore"),
            "keep_with_next": deep(fmt, "KeepWithNext"),
            "list_type": deep(para, "Range", "ListFormat", "ListType"),
            "line_breaks": text.count("\v"),
            "formula_no": formula_no(para, text),
            "west": west,
            "east": east,
        })
    (outdir / f"{path.stem}.wps.json").write_text(
        json.dumps({"path": str(path), "tool": "wps", "paragraphs": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {path.stem}: {len(rows)} 段")
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
    if TRUNCATED:
        print(f"Range.Text 被截断的段落（含星形平面字符）: {TRUNCATED}")
    print("== 取不到的属性 ==")
    for k, v in sorted(FAILED.items(), key=lambda x: -x[1]) or [("（无）", 0)]:
        print(f"  {k}: {v}")
    try:
        app.Quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
