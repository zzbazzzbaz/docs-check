"""对照侧：aspose-words-foss 抽同一组属性。

已知偏差（探查所得，非文档所述）：
  * Font.name = ascii 槽有效值，缺省时回退主题 minorHAnsi（Calibri）
  * Font.name_far_east 仅当 ≠ name 时才有值
  * 段落没写 pStyle 时**不套**默认段落样式，直接回退主题字体
  * 页眉页脚忽略 run 显式写的 eastAsia
"""

from __future__ import annotations

import sys
from pathlib import Path

import aspose.words_foss as aw

from .common import OUT, corpus, write_json

ALIGN = {0: "left", 1: "center", 2: "right", 3: "both"}
LINE_RULE = {0: "atLeast", 1: "exact", 2: "auto"}


class FossDoc:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.doc = aw.Document(str(self.path))
        self.ldm = self.doc.light_document_model

    def para_record(self, p, story: str, ordinal: int) -> dict:
        pf = p.paragraph_format
        runs = []
        for r in p.runs:
            f = r.font
            va = "superscript" if f.superscript else ("subscript" if f.subscript else None)
            runs.append(
                {
                    "text": r.text,
                    "size": f.size or None,
                    "bold": f.bold,
                    "italic": f.italic,
                    "underline": None if not f.underline else "single",
                    "va": va,
                    "ascii": f.name or None,
                    "ea": f.name_far_east or f.name or None,
                    "rstyle": f.style_name or None,
                }
            )
        return {
            "story": story,
            "ordinal": ordinal,
            "text": p.text,
            "style_name": pf.style_name or None,
            "align": ALIGN.get(pf.alignment, str(pf.alignment)),
            "outline": None if pf.outline_level == 9 else pf.outline_level,
            "page_break_before": bool(pf.page_break_before),
            "keep_with_next": bool(pf.keep_with_next),
            "ind_left": pf.left_indent or None,
            "ind_right": pf.right_indent or None,
            "ind_first": pf.first_line_indent or None,
            "ind_first_chars": None,
            "ind_hanging": None,
            "sp_before": pf.space_before or None,
            "sp_after": pf.space_after or None,
            "sp_before_lines": None,
            "sp_after_lines": None,
            "line": pf.line_spacing or None,
            "line_rule": LINE_RULE.get(pf.line_spacing_rule, str(pf.line_spacing_rule)),
            "num_id": 1 if pf.is_list_item else None,
            "runs": runs,
        }

    def _walk(self, children, story: str, out: list, counter: list) -> None:
        for c in children:
            t = getattr(c, "type", None)
            if t == "Paragraph":
                out.append(self.para_record(c, story, counter[0]))
                counter[0] += 1
            elif t == "Table":
                for row in c.rows:
                    for cell in row.cells:
                        self._walk(cell.paragraphs, story, out, counter)
                        if cell.tables:
                            self._walk(cell.tables, story, out, counter)

    def dump(self) -> dict:
        out = {"path": str(self.path), "tool": "foss", "paragraphs": [], "meta": {}}

        counter = [0]
        for sec in self.ldm.sections:
            self._walk(sec.body.children, "main", out["paragraphs"], counter)

        for story, paras in (
            ("header", self.ldm.header_paragraphs),
            ("footer", self.ldm.footer_paragraphs),
        ):
            for i, p in enumerate(paras):
                out["paragraphs"].append(self.para_record(p, story, i))

        out["meta"]["n_paragraphs"] = len(out["paragraphs"])
        out["meta"]["foss_version"] = aw.__version__
        return out


def dump(path) -> dict:
    return FossDoc(path).dump()


def main() -> None:
    args = sys.argv[1:] or [str(p) for p in corpus()]
    for arg in args:
        p = Path(arg)
        write_json(OUT / f"{p.stem}.foss.json", dump(p))
        print("foss:", p.name)


if __name__ == "__main__":
    main()
