"""M0 骨架自检：打包、入口点、异常体系。

这些测试不是"没东西可测"的凑数——它们证明工具链和分层契约真的在工作，
后面每加一层都在这个基础上长大。
"""

import pytest

from thesischeck import __version__, cli, errors


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


def test_cli_reports_unimplemented(capsys: pytest.CaptureFixture[str]) -> None:
    """M1 之前如实返回未实现，不假装能跑。"""
    assert cli.main(["某篇.docx"]) == 2
    assert "尚未实现" in capsys.readouterr().err
