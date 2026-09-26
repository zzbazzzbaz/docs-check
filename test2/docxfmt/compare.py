"""三方对账：自研 vs aspose-words-foss vs WPS 真值。

配对规则：按「同一文本的第 k 次出现」配对，比按顺序对齐稳——
WPS 会把表格行末标记也算成段落，顺序对齐会整体错位。

    python -m docxfmt.compare            # 字段对应分布（校准用）
    python -m docxfmt.compare --report   # 一致率 + 差异样例
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

from .common import OUT, approx, first_family, is_cjk, norm_text, read_json, write_json

UNKNOWN: Counter = Counter()
MISSING = object()

FIELDS = ["对齐", "大纲级别", "行距类型", "行距值",
          "西文字体", "中文字体", "西文字号", "中文字号",
          "西文加粗", "中文加粗", "西文斜体", "中文斜体",
          "西文下划线", "中文下划线", "西文上下标", "中文上下标",
          "首行缩进", "左缩进", "右缩进", "段前", "段后",
          "分页前", "与下段同页", "编号", "可见文本",
          "段落数（含行末标记）", "空段落（文本口径）", "段间空段落数",
          "行内换行数", "公式编号字体", "公式编号字号"]

TOL = {"行距值": 0.6, "首行缩进": 0.6, "左缩进": 0.6, "右缩进": 0.6, "段前": 0.6, "段后": 0.6}

# w:u/@val 与 WPS 的 Font.Underline 枚举都归到一个小区分度
UND_OWN = {"single": "single", "double": "double", "none": None, "": None}
UND_WPS = {0: None, 1: "single", 3: "double"}


def und_own(v):
    return None if not v else UND_OWN.get(str(v).lower(), "其它")


def und_wps(v):
    # 9999999 = wdUndefined，WPS 对超链接/域里的字符返回它，不可比
    return MISSING if v is None or v == 9999999 else UND_WPS.get(int(v), "其它")


def flag_wps(rec, key):
    """WPS 的布尔类属性：None=取不到（跳过），0/-1 → False/True。"""
    v = rec.get(key)
    return MISSING if v is None else bool(v)


def va_wps(rec):
    sup, sub = rec.get("sup"), rec.get("sub")
    if sup is None and sub is None:
        return MISSING
    return "superscript" if sup else ("subscript" if sub else None)


def flag_own(v):
    """自研侧：级联里没写 = 未加粗/未斜体（有效值就是 False）。"""
    return bool(v) if v is not None else False


# 可见文本：保留空格与制表符；去掉段落标记/换行/分页/域分隔，
# 以及 \x01（内嵌对象占位符）、\x02（脚注/批注引用）、\x13\x14\x15（域起/分隔/止）
# 等 Word 内部控制字符——它们不是可见文字。
# WPS 还用控制符表示两个特殊字符，换算成真正的字符。
CTRL = re.compile(r"[\r\n\v\f\a\x07\x0c\x01\x02\x05\x0e\x13\x14\x15]")
WORD_CTRL = {"\x1e": "\u2011", "\x1f": "\u00ad"}   # 不可断开连字符 / 可选连字符


def canon_text(s) -> str:
    return CTRL.sub("", s or "").translate(str.maketrans(WORD_CTRL))


def pair_key(s: str) -> str:
    """配对用键：先按可见文本归一（去掉对象占位符等），再去掉空白。

    直接用原文本配会漏掉「含内嵌图形」的段落：自研文本是 '(3-1)'、WPS 是 '\\x01(3-1)'。
    """
    return norm_text(canon_text(s))


def line_pair(rule, value):
    """行距统一成 (类型, 值)：auto 的值是倍数，其余是磅。"""
    if value is None:
        return (None, None)
    if rule == "auto":
        return ("auto", round(value / 12.0, 2))
    return (rule, round(value, 1))


def pair_by_occurrence(a_list, b_list):
    buckets: dict[str, deque] = {}
    for j, r in enumerate(b_list):
        buckets.setdefault(pair_key(r["text"]), deque()).append(j)
    pairs = []
    for i, r in enumerate(a_list):
        q = buckets.get(pair_key(r["text"]))
        if q:
            pairs.append((i, q.popleft()))
    return pairs


def own_first(rec, kind, key):
    for r in rec["runs"]:
        t = r["text"]
        if kind == "west" and any(c.isascii() and c.isalnum() for c in t):
            return r.get(key)
        if kind == "east" and any(is_cjk(c) for c in t):
            return r.get(key)
    return None


def collect():
    dist = defaultdict(Counter)
    triples = defaultdict(list)
    skipped = 0
    for wf in sorted(OUT.glob("*.wps.json")):
        stem = wf.name[: -len(".wps.json")]
        of, ff = OUT / f"{stem}.own.json", OUT / f"{stem}.foss.json"
        if not (of.exists() and ff.exists()):
            continue
        own, fos, wps = read_json(of), read_json(ff), read_json(wf)

        # 全量列表 + 可配对下标（配对用「非空段落」的文本，空段落走段间序列那条路）
        o_all = [r for r in own["paragraphs"] if r["story"] == "main"]
        f_all = [r for r in fos["paragraphs"] if r["story"] == "main"]
        w_all = list(wps["paragraphs"])
        o_keep = [i for i, r in enumerate(o_all) if pair_key(r["text"])]
        f_keep = [i for i, r in enumerate(f_all) if pair_key(r["text"])]
        # Range.Text 被截断的段落不参与比对：文本可能不完整，配对不可信
        w_keep = [i for i, r in enumerate(w_all)
                  if pair_key(r["text"]) and not r.get("text_truncated")]
        om = [o_all[i] for i in o_keep]
        fm = [f_all[i] for i in f_keep]
        wp = [w_all[i] for i in w_keep]
        fo = dict(pair_by_occurrence(om, fm))
        wo = dict(pair_by_occurrence(om, wp))
        skipped += sum(1 for r in w_all
                       if r.get("text_truncated") and norm_text(r["text"]))

        cur = {"txt": ""}

        def add(field, ov, wv, fv):
            if wv is MISSING:
                UNKNOWN[field] += 1
                return
            # WPS 对超链接/域里的字符返回「未定义」：字体是空串、字号与下划线 9999999。
            # 大纲级别的 None 是正常值（正文），不算未定义。
            if field in ("西文字体", "中文字体") and not wv and ov:
                UNKNOWN[field] += 1
                return
            if field.endswith("字号") and wv == 9999999.0:
                UNKNOWN[field] += 1
                return
            dist[field][(ov, wv)] += 1
            triples[field].append((ov, wv, fv, stem, cur["txt"][:24]))

        # 段落序列：WPS 的 Paragraphs 在每个表格行末多一个空段落，按位置对齐
        # （自研下标 + 它之前出现过的行末标记数 = WPS 下标）
        row_marks = sum(1 for r in o_all if r.get("row_end"))
        add("段落数（含行末标记）", len(o_all) + row_marks, len(w_all), stem)
        j = 0
        for i, r in enumerate(o_all):
            if j >= len(w_all):
                break
            add("空段落（文本口径）", r.get("text_empty"), w_all[j].get("text_empty"),
                f"{stem[:16]} 第{i + 1}段")
            j += 2 if r.get("row_end") else 1

        # 段间序列：配上的相邻两段之间夹了几个空段落（「其后正好 1 个空段落」那类规则要的就是这个）
        matched = sorted(wo.items())
        for (a, wa), (b, wb) in zip(matched, matched[1:]):
            ai, wi, bi, wj = o_keep[a], w_keep[wa], o_keep[b], w_keep[wb]
            if wj <= wi:
                continue
            gap = o_all[ai:bi]
            add("段间空段落数",
                sum(1 for r in o_all[ai + 1:bi] if r.get("text_empty")),
                sum(1 for r in w_all[wi + 1:wj] if r.get("text_empty"))
                - sum(1 for r in gap if r.get("row_end")),
                f"{stem[:18]} 第{ai + 1}~{bi + 1}段间")

        for oi, ro in enumerate(om):
            wi = wo.get(oi)
            if wi is None:
                continue
            W = wp[wi]
            F = fm[fo[oi]] if oi in fo else None
            cur["txt"] = ro["text"]

            add("对齐", ro["align"], W.get("align"), F["align"] if F else None)
            add("大纲级别", ro["outline"], W.get("outline"), F["outline"] if F else None)
            ok_, ov = line_pair(ro["line_rule"], ro["line"])
            fk, fv = line_pair(F["line_rule"], F["line"]) if F else (None, None)
            add("行距类型", ok_, W.get("line_rule"), fk)
            add("行距值", ov, W.get("line"), fv)

            for kind, label in (("west", "西文"), ("east", "中文")):
                # 整段是 OMML 公式时没有 w:r（字符都在 m:r 里），字符级属性无从采样，跳过
                if not ro["runs"]:
                    continue
                o_f = own_first(ro, kind, "ascii" if kind == "west" else "ea")
                Wk = W.get(kind) or {}
                w_f = Wk.get("font") if kind == "west" else (Wk.get("ea") or Wk.get("font"))
                f_f = own_first(F, kind, "ascii" if kind == "west" else "ea") if F else None
                add(f"{label}字体", first_family(o_f or ""), first_family(w_f or ""),
                    first_family(f_f or ""))
                add(f"{label}字号",
                    round(own_first(ro, kind, "size") or 0, 1),
                    round(Wk.get("size") or 0, 1),
                    round(own_first(F, kind, "size") or 0, 1) if F else None)
                # run 级属性：采样点与字体一致（西文槽取第一个含 ASCII 字母数字的 run，中文槽同理）
                add(f"{label}加粗", flag_own(own_first(ro, kind, "bold")),
                    flag_wps(Wk, "bold"), flag_own(own_first(F, kind, "bold")) if F else None)
                add(f"{label}斜体", flag_own(own_first(ro, kind, "italic")),
                    flag_wps(Wk, "italic"), flag_own(own_first(F, kind, "italic")) if F else None)
                add(f"{label}下划线", und_own(own_first(ro, kind, "underline")),
                    und_wps(Wk.get("underline")),
                    und_own(own_first(F, kind, "underline")) if F else None)
                add(f"{label}上下标", own_first(ro, kind, "va"), va_wps(Wk),
                    own_first(F, kind, "va") if F else None)

            for fld, okey, wkey in (("首行缩进", "ind_first", "first_indent"),
                                    ("左缩进", "ind_left", "left_indent"),
                                    ("右缩进", "ind_right", "right_indent"),
                                    ("段前", "sp_before", "space_before"),
                                    ("段后", "sp_after", "space_after")):
                add(fld, round(ro.get(okey) or 0, 1), round(W.get(wkey) or 0, 1),
                    round(F.get(okey) or 0, 1) if F else None)

            add("分页前", ro["page_break_before"],
                flag_wps(W, "page_break_before"),
                F["page_break_before"] if F else None)
            add("与下段同页", ro["keep_with_next"],
                flag_wps(W, "keep_with_next"),
                F["keep_with_next"] if F else None)
            add("编号", ro["num_id"] is not None,
                MISSING if W.get("list_type") is None else bool(W["list_type"]),
                (F["num_id"] is not None) if F else None)
            add("可见文本", canon_text(ro["text"]), canon_text(W["text"]),
                canon_text(F["text"]) if F else None)
            add("行内换行数", ro["line_breaks"],
                MISSING if W.get("line_breaks") is None else W["line_breaks"],
                F.get("line_breaks") if F else None)

            # 公式编号的字体/字号：按编号所在字符采样，两侧位置口径一致
            # （整段是 OMML 公式时没有 w:r，字符级属性无从采样，跳过）
            o_fn, w_fn = ro.get("formula_no") or {}, W.get("formula_no") or {}
            if (w_fn or o_fn) and ro["runs"]:
                add("公式编号字体", first_family(o_fn.get("ascii") or ""),
                    first_family(w_fn.get("font") or ""), None)
                add("公式编号字号", round(o_fn.get("size") or 0, 1),
                    round(w_fn.get("size") or 0, 1), None)
    return dist, triples, skipped


def eq(field, a, b) -> bool:
    if a is None or b is None:
        return a == b
    if field in TOL:
        return approx(a, b, TOL[field])
    if field.endswith("字号"):
        return approx(a, b, 0.2)
    return a == b


def main() -> None:
    dist, triples, skipped = collect()
    if not dist:
        print("没有 out/*.wps.json —— 先跑 ./run.sh")
        return

    if "--report" not in sys.argv:
        for fld in FIELDS:
            if fld not in dist:
                continue
            print(f"\n=== {fld}（自研 → WPS）最多的 6 种 ===")
            for (a_, b_), n in dist[fld].most_common(6):
                print(f"  {'✓' if a_ == b_ else ' '} {a_!r:<28} → {b_!r:<26} {n}")
        return

    out = {"per_field": {}, "own_ne_wps": [], "foss_ne_wps": []}
    print("=== 自研 / foss 分别与 WPS(真值) 对照 ===\n")
    print(f"{'字段':<10}{'比对':>6}{'自研=WPS':>12}{'foss=WPS':>12}")
    tot = [0, 0, 0]
    for fld in FIELDS:
        rows = triples.get(fld, [])
        if not rows:
            continue
        n = len(rows)
        o = sum(1 for ov, wv, _, _, _ in rows if eq(fld, ov, wv))
        f_ = sum(1 for _, wv, fv, _, _ in rows if eq(fld, fv, wv))
        tot[0] += n
        tot[1] += o
        tot[2] += f_
        out["per_field"][fld] = {"n": n, "own": o, "foss": f_}
        print(f"{fld:<10}{n:>6}{o:>7} ({o / n * 100:6.2f}%){f_:>7} ({f_ / n * 100:6.2f}%)")
        for ov, wv, fv, stem, txt in rows:
            if not eq(fld, ov, wv) and len(out["own_ne_wps"]) < 40:
                out["own_ne_wps"].append([fld, stem, txt, ov, wv, fv])
            if not eq(fld, fv, wv) and len(out["foss_ne_wps"]) < 15:
                out["foss_ne_wps"].append([fld, stem, txt, ov, wv, fv])

    if tot[0]:
        print(f"\n{'合计':<10}{tot[0]:>6}{tot[1]:>7} ({tot[1] / tot[0] * 100:6.2f}%)"
              f"{tot[2]:>7} ({tot[2] / tot[0] * 100:6.2f}%)")
    write_json(OUT / "compare.json",
               {"totals": {"n": tot[0], "own_ok": tot[1], "foss_ok": tot[2]}, **out})

    print("\nWPS 返回「未定义」而跳过的字段：", dict(UNKNOWN))
    if skipped:
        print(f"WPS 文本被截断、未参与比对的段落：{skipped}")
    print("\n自研 ≠ WPS 的样例：")
    for r in out["own_ne_wps"][:12]:
        print(f"  {r[0]} {r[1][:20]:<22} {r[2]!r:<24} 自研={r[3]!r} WPS={r[4]!r} foss={r[5]!r}")
    print("\nfoss ≠ WPS 的样例：")
    for r in out["foss_ne_wps"][:8]:
        print(f"  {r[0]} {r[1][:20]:<22} {r[2]!r:<24} 自研={r[3]!r} WPS={r[4]!r} foss={r[5]!r}")


if __name__ == "__main__":
    main()
