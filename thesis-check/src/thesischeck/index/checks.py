"""L3 索引自检：`DocumentIndex` 的不变量。

索引没有 WPS 裁判（WPS 给不了块类型与语义分区），所以靠不变量自证。口径照搬参考实现
`test2/docxfmt/index_check.py`：

- 图 / 表编号重复**只提示不判错**——正文里「图4-1 所示」也匹配图题模式，重号可能是文档歧义，
  由正文规则再收缩，不能在这一层当成缺陷。
- 引用抽不到（定位不到正文区）时给一条提示，不静默当作「没有引用」。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from ..parse.model import Document, Para
from .document_index import DocumentIndex, ModuleSpan, matches_module


class Severity(StrEnum):
    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True, slots=True)
class IndexViolation:
    """一条不变量违规。`check` 是不变量名，`severity` 区分失败与提示。"""

    check: str
    severity: Severity
    detail: str


def _covered_paragraphs(doc: Document) -> list[int]:
    """块序列铺开的段落号（表格按行 / 格下钻）。"""
    out: list[int] = []
    for block in doc.blocks:
        if isinstance(block, Para):
            out.append(block.id)
        else:
            for row in block.rows:
                for cell in row:
                    out.extend(para.id for para in cell.paragraphs)
    return out


def _module_span_pairs(modules: tuple[ModuleSpan, ...]) -> list[tuple[ModuleSpan, ModuleSpan]]:
    return list(pairwise(modules))


def check_index(doc: Document, index: DocumentIndex) -> tuple[IndexViolation, ...]:
    """对索引跑全部不变量，返回违规清单（空 = 全过）。"""
    out: list[IndexViolation] = []
    total = len(doc.paragraphs)
    modules = index.modules

    # 1) 块覆盖：段落号恰好铺满 0..n-1，不重不漏
    covered = _covered_paragraphs(doc)
    if sorted(covered) != list(range(total)):
        out.append(
            IndexViolation(
                "块覆盖完整",
                Severity.FAIL,
                f"块覆盖 {len(covered)} 个段号，应为 {total} 个且不重不漏",
            )
        )

    # 2) 模块区间连续、不重叠、覆盖全篇
    contiguous = (
        bool(modules)
        and modules[0].start == 0
        and modules[-1].end == total - 1
        and all(right.start == left.end + 1 for left, right in _module_span_pairs(modules))
    )
    if not contiguous:
        detail = [(span.name, span.start, span.end) for span in modules][:4]
        out.append(IndexViolation("模块区间连续", Severity.FAIL, f"区间不连续或不覆盖全篇：{detail}…"))

    # 3) 模块边界段落的文本对得上该模块的关键文本（封面无边界文本，跳过）
    for span in modules:
        if span.name == "封面" or not 0 <= span.start < total:
            continue
        if not matches_module(span.name, doc.paragraphs[span.start].text):
            out.append(
                IndexViolation(
                    "模块边界文本对得上",
                    Severity.FAIL,
                    f"{span.name} 的边界段 {span.start} 文本与关键文本不符",
                )
            )

    body = next((span for span in modules if span.name == "正文"), None)

    # 4) 章：按段号有序、都在正文区
    starts = [chapter.start for chapter in index.chapters]
    if starts != sorted(starts) or (
        body is not None and any(not (body.start <= start <= body.end) for start in starts)
    ):
        out.append(IndexViolation("章有序且在正文区", Severity.FAIL, "章不在正文区或次序乱"))

    # 5) 图 / 表编号重复：**只提示不判错**
    for kind, refs in (("图", index.floats.figures), ("表", index.floats.tables)):
        duplicates = [
            no for no, count in Counter(ref.no for ref in refs if ref.no is not None).items() if count > 1
        ]
        if duplicates:
            out.append(
                IndexViolation(
                    "图/表编号重复",
                    Severity.WARN,
                    f"{kind}编号重复：{sorted(str(no) for no in duplicates)[:4]}",
                )
            )

    # 6) 引用：编号唯一、order 从 1 连续、都在正文区
    if index.citations is None:
        out.append(IndexViolation("引用唯一且顺序一致", Severity.WARN, "定位不到正文区，引用无法判定"))
    else:
        numbers = [citation.no for citation in index.citations]
        orders = [citation.order for citation in index.citations]
        outside = body is not None and any(
            not (body.start <= citation.para <= body.end) for citation in index.citations
        )
        if len(set(numbers)) != len(numbers) or orders != list(range(1, len(index.citations) + 1)) or outside:
            out.append(
                IndexViolation(
                    "引用唯一且顺序一致", Severity.FAIL, "引用编号重复 / order 不连续 / 不在正文区"
                )
            )

    # 7) 目录条目层级合法（1/2/3）
    if any(entry.level not in (1, 2, 3) for entry in index.toc_entries):
        out.append(IndexViolation("目录条目层级合法", Severity.FAIL, "目录条目层级不在 1/2/3"))

    return tuple(out)
