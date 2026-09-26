"""`DocumentIndex` 的验证：不变量检查 + 独立重算。

这一块**没有 WPS 裁判**（WPS 给不了块类型与语义分区），所以换三条路：
  1. **不变量**：区间连续不重叠、编号唯一、东西都在该在的区里；
  2. **跨模块对齐**：段落数与 TOC 域跨度取自已由 WPS 验证过的产物；
  3. **独立重算**：用另一种走法（只走顶层段落块）重算模块边界，与 `index.py`（全段扫描）比。

    python -m docxfmt.index_check [--report]
"""

from __future__ import annotations

import sys
from collections import Counter
from .common import OUT, read_json
from .index import MODULES, TOC_STYLE, key_text

CHECKS = ["块覆盖完整", "模块区间连续", "模块边界文本对得上", "章有序且在正文区",
          "引用唯一且顺序一致", "目录条目层级合法", "独立重算模块边界一致"]
WARNS = ["图/表编号重复"]        # 文档本身可能就有重号（正文引用也会匹配图题模式），只提示不判错


def recompute_modules(idx: dict, recs: list[dict]) -> list[tuple[str, int]]:
    """独立重算模块边界：只看**顶层段落块**（`kind == "p"`），与 index.py 的全段扫描是两种走法。

    index.py 扫的是全部段落（含表格里的），这里只看不在表格里的顶层段落 ——
    如果某个模块边界是从表格内部捞出来的，两次结果就会不一致，正好暴露出来。
    """
    top = [b["paras"][0] for b in idx["blocks"] if b["kind"] == "p" and len(b["paras"]) == 1]
    got = []
    for name, pred in MODULES:
        hit = next((i for i in top
                    if pred(key_text(recs[i]["text"]))
                    and not TOC_STYLE.match((recs[i].get("style_name") or "").strip().lower())),
                   None)
        if hit is not None:
            got.append((name, hit))
    return got


def check_one(stem: str) -> dict:
    own = read_json(OUT / f"{stem}.own.json")
    idx = read_json(OUT / f"{stem}.ownindex.json")
    recs = [r for r in own["paragraphs"] if r["story"] == "main"]
    n = len(recs)
    fail = {c: False for c in CHECKS}
    detail = []

    # 1) 块覆盖：段落号恰好铺满 0..n-1
    covered = [p for b in idx["blocks"] for p in b["paras"]]
    if sorted(covered) != list(range(n)):
        fail["块覆盖完整"] = True
        detail.append(f"块覆盖不上：{len(covered)} / 应有 {n}")

    # 2) 模块区间连续、覆盖全篇
    mods = idx["modules"]
    ok = bool(mods) and mods[0]["from"] == 0 and mods[-1]["to"] == n - 1
    ok = ok and all(b["from"] == a["to"] + 1 for a, b in zip(mods, mods[1:]))
    if not ok:
        fail["模块区间连续"] = True
        detail.append(f"模块区间不连续（{[(m['name'], m['from'], m['to']) for m in mods][:4]}…）")

    # 3) 模块边界段落必须匹配该模块的关键文本
    bad = [m["name"] for m in mods if m["name"] != "封面"
           and not dict(MODULES).get(m["name"], lambda _: False)(key_text(recs[m["from"]]["text"]))]
    if bad:
        fail["模块边界文本对得上"] = True
        detail.append(f"边界文本不匹配：{bad}")

    zone = next((m for m in mods if m["name"] == "正文"), None)

    # 4) 章：按段号有序、都在正文区
    seq = [c["para"] for c in idx["chapters"]]
    if seq != sorted(seq) or (zone and any(not (zone["from"] <= p <= zone["to"]) for p in seq)):
        fail["章有序且在正文区"] = True
        detail.append("章不在正文区或次序乱")

    # 5) 图/表编号重复：**只提示不判错** —— 正文里「图4-1 所示」也匹配图题模式，
    #    重号可能是文档歧义（规则层要靠 TXT-38 的"在图下方"再收缩），不一定是缺陷
    warn = []
    for kind in ("figure", "table"):
        dup = [k for k, v in Counter(f["no"] for f in idx["floats"][kind]).items() if v > 1]
        if dup:
            warn.append(f"{kind} 编号重复：{dup[:4]}")

    # 6) 引用：编号唯一、order 连续、都在正文区
    cit = idx["citations"]
    nos = [c["no"] for c in cit]
    if (len(set(nos)) != len(nos) or [c["order"] for c in cit] != list(range(1, len(cit) + 1))
            or (zone and any(not (zone["from"] <= c["para"] <= zone["to"]) for c in cit))):
        fail["引用唯一且顺序一致"] = True
        detail.append("引用编号重复 / order 不连续 / 不在正文区")

    # 7) 目录条目层级合法
    if any(e["level"] not in (1, 2, 3) for e in idx["toc_entries"]):
        fail["目录条目层级合法"] = True
        detail.append("目录条目层级不合法")

    # 8) 独立重算模块边界
    got = recompute_modules(idx, recs)
    mine = [(m["name"], m["from"]) for m in mods if m["name"] != "封面"]
    if got != mine:
        fail["独立重算模块边界一致"] = True
        detail.append(f"重算不一致：重算 {got} ≠ 索引 {mine}")
    return {"stem": stem, "fail": fail, "detail": detail, "warn": warn}


def main() -> None:
    stems = sorted(f.name[: -len(".ownindex.json")] for f in OUT.glob("*.ownindex.json"))
    if not stems:
        print("没有 out/*.ownindex.json —— 先跑 python -m docxfmt.index corpus/*.docx")
        return
    rows = [check_one(s) for s in stems]
    n = len(stems)

    print("=== DocumentIndex 不变量检查（无 WPS 裁判，靠自证）===\n")
    for c in CHECKS:
        bad = sum(1 for r in rows if r["fail"][c])
        print(f"{c:<24}{n - bad:>5}/{n:<5}{'' if not bad else '  ← ' + str(bad) + ' 篇不通过'}")
    for c in WARNS:
        bad = sum(1 for r in rows if r.get("warn"))
        print(f"{c:<24}{n - bad:>5}/{n:<5}{'' if not bad else '  ← 提示 ' + str(bad) + ' 篇有重号'}")

    if "--report" in sys.argv and any(r["detail"] for r in rows):
        print("\n=== 不通过的明细 ===")
        for r in rows:
            if r["detail"]:
                print(f"\n【{r['stem'][:36]}】")
                for d in r["detail"]:
                    print(f"   {d}")


if __name__ == "__main__":
    main()
