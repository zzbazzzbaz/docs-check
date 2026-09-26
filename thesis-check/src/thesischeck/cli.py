"""命令行入口。

生产链路接 `pipeline.review()`；`--compat-dump` 是**只用于调试 / 等价性关卡**的旁路，
把解析结果渲染成 `test2` 快照的形状，不进入生产链路。
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import ThesisCheckError
from .parse import compat
from .parse.document import parse_document
from .parse.package import Package
from .pipeline import review

SUITES = ("own", "ownpages", "ownborders", "owntextbox", "ownindex")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thesis-check", description="毕业论文格式自动审核")
    parser.add_argument("docx", nargs="?", help="待审核的 .docx")
    parser.add_argument("-o", "--outdir", default="out", help="产物目录（默认 out/）")
    parser.add_argument(
        "--compat-dump",
        choices=SUITES,
        metavar="SUITE",
        help="调试用：按 test2 快照形状输出解析结果（own / ownpages / ownborders / owntextbox / ownindex）",
    )
    parser.add_argument(
        "--unknown-elements",
        action="store_true",
        help="调试用：打印解析器未认识（document.xml 里出现但未专门处理）的元素清单后退出",
    )
    parser.add_argument("--version", action="version", version=f"thesischeck {__version__}")
    args = parser.parse_args(argv)

    if args.docx is None:
        parser.print_help()
        return 0

    if args.unknown_elements:
        with Package.open(args.docx) as pkg:
            doc = parse_document(pkg)
        for name in doc.unknown_elements:
            print(name)
        return 0

    if args.compat_dump is not None:
        with Package.open(args.docx) as pkg:
            doc = parse_document(pkg)
            dumped = compat.dump_suite(args.compat_dump, pkg, doc)
        json.dump(dumped, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    try:
        result = review(Path(args.docx), Path(args.outdir))
    except ThesisCheckError as exc:
        print(f"无法审核：{exc}", file=sys.stderr)
        return 2
    print(f"问题清单：{result.issues_json}")
    print(f"审核报告：{result.report_html}")
    print(f"标注版文档：{result.marked_docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
