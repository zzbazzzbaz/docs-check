"""M0 骨架自检：打包、入口点、异常体系。

这些测试不是"没东西可测"的凑数——它们证明工具链和分层契约真的在工作，
后面每加一层都在这个基础上长大。
"""

import zipfile
from pathlib import Path

import pytest

from thesischeck import __version__, cli, errors
from thesischeck.parse import package as pkg


def test_version() -> None:
    assert __version__


def test_error_hierarchy() -> None:
    assert issubclass(errors.BadDocument, errors.ThesisCheckError)
    assert issubclass(errors.ParseError, errors.ThesisCheckError)
    assert issubclass(errors.RuleError, errors.ThesisCheckError)


def test_parse_error_carries_part() -> None:
    exc = errors.ParseError("word/document.xml", "缺 body")
    assert "word/document.xml" in str(exc)
    assert exc.part == "word/document.xml"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_without_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    assert "thesis-check" in capsys.readouterr().out


def test_cli_reports_bad_document(capsys: pytest.CaptureFixture[str]) -> None:
    """坏输入如实返回 2，并给可读原因，不抛堆栈。"""
    assert cli.main(["某篇.docx"]) == 2
    assert "无法审核" in capsys.readouterr().err


def test_cli_prints_unknown_elements(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """调试开关 `--unknown-elements` 打印完整未认识元素清单（FR-10.4）。"""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document = (
        f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body><w:p><w:ins/></w:p></w:body></w:document>'
    ).encode()
    path = tmp_path / "u.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(pkg.PART_CONTENT_TYPES, b'<?xml version="1.0"?><Types/>')
        archive.writestr(pkg.PART_DOCUMENT, document)

    assert cli.main([str(path), "--unknown-elements"]) == 0
    assert "ins" in capsys.readouterr().out
