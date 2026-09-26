"""编排：把各层串起来（parse → semantics → index → rules → report）。

放在最上层是有意的：`cli` 与 `web` 都只调这里，不各自拼流程，
这样两条入口的结论一定一致。

M1 起接各层；在此之前显式失败，不假装能跑。
"""

from pathlib import Path


def review(docx: Path, outdir: Path) -> None:
    """审核一篇文档，产出 issues.json / report.html / 标注版 docx。"""
    raise NotImplementedError(f"M1：解析层实现后接上（{docx} → {outdir}）")
