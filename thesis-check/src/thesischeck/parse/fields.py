"""域采集：把正文故事区的**真实域**拼出来，并给出每个域跨到哪几段。

口径照搬 `test2/docxfmt/own.py` 的 `OwnDoc.fields`：`w:fldChar` 的 begin/end 配成对
（代码取该域第一段 `w:instrText` 的首个词大写），`w:fldSimple` 记成单段域；域可以跨段、
可以嵌套。文本框与 `mc:Fallback` 里的不算。

WPS 的 `doc.Fields` 还会把 `w:object` / `w:hyperlink` / `w:pict` 合成为 EMBED / HYPERLINK /
SHAPE 域，那是它自己的口径；规则判定只用这里的真实域，所以合成域不采集。
"""

from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from .document import _in_fallback, _inside_txbx, object_counts, para_text
from .effective import w
from .model import Field


def parse_fields(paragraphs: Sequence[etree._Element]) -> tuple[Field, ...]:
    """采集正文故事区的真实域；`paragraphs` 按段号排列（下标即段号）。

    页眉页脚里的域不走这里，由 `section.py` 单独处理。
    """
    # 先把域的范围与代码收成元组，冻结成 Field 前还要算「内容结束段」
    raw: list[tuple[str, int, int, etree._Element]] = []
    stack: list[tuple[int, str | None, etree._Element]] = []
    for index, p in enumerate(paragraphs):
        for el in p.iter():
            if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
                continue
            if el.tag == w("fldChar"):
                fld_type = el.get(w("fldCharType"))
                if fld_type == "begin":
                    stack.append((index, None, el))
                elif fld_type == "end" and stack:
                    start, code, marker = stack.pop()
                    raw.append((code or "", start, index, marker))
            elif el.tag == w("instrText") and stack and stack[-1][1] is None:
                text = (el.text or "").strip()
                if text:
                    start, _, marker = stack[-1]
                    stack[-1] = (start, text.split()[0].upper(), marker)
            elif el.tag == w("fldSimple"):
                instr = (el.get(w("instr")) or "").strip()
                if instr:
                    raw.append((instr.split()[0].upper(), index, index, el))

    raw.sort(key=lambda item: (item[1], item[0]))

    fields: list[Field] = []
    for code, start, end, marker in raw:
        # 结束标记所在段若只有标记、没有别的内容，域结果其实结束在上一段
        # （WPS 的 Field.Result.End 就是这么给的，TOC 跨度全靠它）
        tail = paragraphs[end]
        end_content = end if para_text(tail) or object_counts(tail).any else max(start, end - 1)
        fields.append(Field(code=code, start=start, end=end, end_content=end_content, xml=marker))
    return tuple(fields)
