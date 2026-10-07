"""自研侧的块序列与整篇只读索引（`DocumentIndex`）。

规则文档（`docs/规则/9-整体.md`）约定：在语义层之后、规则之前构建一次性只读索引，
字段为 `modules` / `chapters` / `floats` / `citations` / `toc_entries`。

**这一块没有 WPS 裁判**（WPS 给不了块类型、也给不了"这段属于哪个模块"的语义分区），
所以验证方式不同：见 `index_check.py` 的不变量检查与独立重算。

    python -m docxfmt.index [docx ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from lxml import etree

from .common import OUT, corpus, w, write_json
from .own import TAG, ZIP_DOC, OwnDoc, iter_paragraphs, para_text

# 模块边界的关键文本（README 通用口径：识别锚点要宽松，忽略空白）
MODULES = [
    ("中文摘要", lambda t: t == "摘要"),
    ("英文摘要", lambda t: t == "ABSTRACT"),
    ("目录", lambda t: t == "目录"),
    ("正文", lambda t: re.match(r"^第[一二三四五六七八九十]+章", t) is not None),
    ("参考文献", lambda t: t == "参考文献"),
    ("致谢", lambda t: t == "致谢"),
    ("附录", lambda t: t.startswith("附录")),
]
CHAPTER = re.compile(r"^第([一二三四五六七八九十]+|\d+)章")
CN_NUM = {c: i for i, c in enumerate("一二三四五六七八九十", 1)}


def chapter_no(text: str) -> int | None:
    """一级标题的章号：支持中文数字（第一章）与阿拉伯数字（第3章）。"""
    m = CHAPTER.match(text)
    if m is None:
        return None
    g = m.group(1)
    return int(g) if g.isdigit() else CN_NUM.get(g[0], 0) or None

FIGURE = re.compile(r"^图\s*(\d+)\s*-\s*(\d+)")
TABLE = re.compile(r"^表\s*(\d+)\s*-\s*(\d+)")
FORMULA_NO = re.compile(r"\((\d+)\s*-\s*(\d+)\)")
TOC_STYLE = re.compile(r"^toc\s*([123])$")
CITE = re.compile(r"^\[?\s*(\d+(?:\s*[-–,，]\s*\d+)*)\s*\]?$")
ZW = "\u200b"


def key_text(s: str) -> str:
    """识别锚点用：去所有空白。"""
    return re.sub(r"\s+", "", s or "").lstrip(ZW)


def blocks(body) -> list[dict]:
    """文档流的块序列：`w:p` 与 `w:tbl` 的交错（段落编号与 `iter_paragraphs` 一致）。"""
    out: list[dict] = []

    def walk(node, pi: int, top: bool) -> int:
        for child in node:
            if not isinstance(child.tag, str):
                continue
            tag = TAG(child)
            if tag == "p":
                out.append({"kind": "p", "paras": [pi]})
                pi += 1
            elif tag == "tbl":
                # 不能对 tbl 根直接调 iter_paragraphs（它只看子元素是 p/tbl/sdt 的情况，
                # 而表下面是 tr → 会数出 0 个）。要按 tr/tc 下钻。
                n = sum(len(iter_paragraphs(tc))
                        for tr in child.findall(w("tr")) for tc in tr.findall(w("tc")))
                rows = len(child.findall(w("tr")))
                cols = max((len(tr.findall(w("tc"))) for tr in child.findall(w("tr"))), default=0)
                out.append({"kind": "tbl", "paras": list(range(pi, pi + n)),
                            "rows": rows, "cols": cols})
                pi += n
            elif tag == "sdt":
                content = child.find(w("sdtContent"))
                if content is not None:
                    pi = walk(content, pi, top)     # 段号计数器要接着走，不能重置
        return pi

    walk(body, 0, True)
    for i, b in enumerate(out):
        b["i"] = i
    return out


class DocIndex:
    def __init__(self, path: Path):
        self.doc = OwnDoc(path)
        body = etree.fromstring(self.doc.z.read(ZIP_DOC)).find(w("body"))
        self.paras = list(iter_paragraphs(body))
        self.blocks = blocks(body)
        self.records = [self.doc.para_record(p, "main", i, t, r)
                        for i, (p, t, r) in enumerate(self.paras)]
        self.fields = self.doc.fields(body)
        for f in self.fields:
            if not f["synthetic"] and 0 <= f["para"] < len(self.records):
                self.records[f["para"]]["field_codes"].append(f["code"])
        self.toc = next((f for f in self.fields if f.get("code") == "TOC"), None)

    # ── 模块分区 ────────────────────────────────────────────
    def _is_toc_like(self, i: int) -> bool:
        """只按样式名判「是不是目录条目」。

        不在 TOC 域区间上判：目录标题那段往往就是 TOC 域的 begin 段，
        按区间排会把它一起排掉（`table-of-contents-entry-format` 就踩了这个）。
        """
        return bool(TOC_STYLE.match((self.records[i]["style_name"] or "").strip().lower()))

    def in_toc_range(self, i: int) -> bool:
        return bool(self.toc and self.toc["para"] <= i <= self.toc["end_para"])

    def modules(self) -> list[dict]:
        bounds: list[tuple[str, int]] = []
        for name, pred in MODULES:
            hit = next((i for i, r in enumerate(self.records)
                        if pred(key_text(r["text"])) and not self._is_toc_like(i)), None)
            if hit is not None:
                bounds.append((name, hit))
        out = []
        prev = ("封面", 0)
        for name, start in bounds:
            if start > prev[1]:
                out.append({"name": prev[0], "from": prev[1], "to": start - 1})
            prev = (name, start)
        out.append({"name": prev[0], "from": prev[1], "to": len(self.records) - 1})
        return out

    # ── 其余索引 ─────────────────────────────────────────────
    def chapters(self) -> list[dict]:
        """一级标题候选：**宽松收集**（正文区内、文本以「第…章」开头、不是目录条目）。

        按 `9-整体.md` 的纪律「索引宽松收集、规则负责收缩」：这里不做严格筛选，
        把 `outline` / `style_name` / `is_heading1`（大纲级别 1 级）一并带上，由规则收缩。
        """
        zone = next((m for m in self.modules() if m["name"] == "正文"), None)
        if zone is None:
            return []
        out = []
        for i in range(zone["from"], zone["to"] + 1):
            if self._is_toc_like(i):
                continue
            no = chapter_no(key_text(self.records[i]["text"]))
            if no:
                r = self.records[i]
                out.append({"no": no, "text": key_text(r["text"])[:24], "para": i,
                            "outline": r["outline"], "style_name": r["style_name"],
                            "is_heading1": r["outline"] == 0})
        for n, ch in enumerate(out):        # 区间到下一章为止
            ch["to"] = out[n + 1]["para"] - 1 if n + 1 < len(out) else zone["to"]
        return out

    def in_body(self, i: int) -> bool:
        zone = next((m for m in self.modules() if m["name"] == "正文"), None)
        return bool(zone and zone["from"] <= i <= zone["to"])

    def floats(self) -> dict:
        fig, tab, fno, fobj = [], [], [], 0
        for i, r in enumerate(self.records):
            t = key_text(r["text"])
            m = FIGURE.match(t)
            if m:
                fig.append({"no": f"{m.group(1)}-{m.group(2)}", "para": i})
            m = TABLE.match(t)
            if m:
                tab.append({"no": f"{m.group(1)}-{m.group(2)}", "para": i})
            if r["has_formula"]:
                fobj += r["objects"]["ole"] + r["objects"]["omath"]
                m = FORMULA_NO.search(r["text"])
                fno.append({"no": f"{m.group(1)}-{m.group(2)}" if m else None, "para": i})
        return {"figure": fig, "table": tab, "formula": fno, "formula_objects": fobj}

    def citations(self) -> list[dict]:
        """正文区的引用标注（`w:vertAlign=superscript` 的 run），按首次出现排序。"""
        seen: dict[int, int] = {}
        out: list[dict] = []
        for i, r in enumerate(self.records):
            if not self.in_body(i):
                continue
            for run in r["runs"]:
                if run["va"] != "superscript" or not run["text"].strip():
                    continue
                m = CITE.match(run["text"].strip())
                if not m:
                    continue
                for part in re.split(r"[,，]", m.group(1)):
                    part = part.strip()
                    nums = [int(x) for x in re.split(r"[-–]", part) if x.strip().isdigit()]
                    if len(nums) == 2:
                        nums = list(range(nums[0], nums[1] + 1))
                    for n in nums:
                        if n not in seen:
                            seen[n] = len(seen) + 1
                            out.append({"no": n, "para": i, "order": seen[n]})
        return out

    def toc_entries(self) -> list[dict]:
        out = []
        for i, r in enumerate(self.records):
            if not self.in_toc_range(i):
                continue
            m = TOC_STYLE.match((r["style_name"] or "").strip().lower())
            if m:
                out.append({"level": int(m.group(1)), "text": r["text"][:40], "para": i})
        return out

    def dump(self) -> dict:
        return {"path": str(self.doc.path), "tool": "own", "blocks": self.blocks,
                "modules": self.modules(), "chapters": self.chapters(),
                "floats": self.floats(), "citations": self.citations(),
                "toc_entries": self.toc_entries()}


def dump(path) -> dict:
    return DocIndex(Path(path)).dump()


def main() -> None:
    args = sys.argv[1:] or [str(p) for p in corpus()]
    for arg in args:
        p = Path(arg)
        data = dump(p)
        write_json(OUT / f"{p.stem}.ownindex.json", data)
        print(f"index: {p.name}  块 {len(data['blocks'])} 模块 {len(data['modules'])} "
              f"章 {len(data['chapters'])} 图 {len(data['floats']['figure'])} "
              f"表 {len(data['floats']['table'])} 引用 {len(data['citations'])} "
              f"目录条目 {len(data['toc_entries'])}")


if __name__ == "__main__":
    main()
