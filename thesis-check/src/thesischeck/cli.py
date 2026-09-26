"""命令行入口。

M0 只验证打包与入口点；解析实现后这里接 `pipeline.review()`。
"""

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thesis-check", description="毕业论文格式自动审核")
    parser.add_argument("docx", nargs="?", help="待审核的 .docx")
    parser.add_argument("-o", "--outdir", default="out", help="产物目录（默认 out/）")
    parser.add_argument("--version", action="version", version=f"thesischeck {__version__}")
    args = parser.parse_args(argv)

    if args.docx is None:
        parser.print_help()
        return 0

    # M1 起接 pipeline.review()；现在如实说明，不假装能跑
    print("解析尚未实现（M1）。当前只验证命令行与打包。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
