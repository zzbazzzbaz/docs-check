from __future__ import annotations

import json
import re
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
OUT = ROOT / "out"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def a(tag: str) -> str:
    return f"{{{A}}}{tag}"


def m(tag: str) -> str:
    return f"{{{M}}}{tag}"


def wp(tag: str) -> str:
    return f"{{{WP}}}{tag}"


def TAG(el) -> str:
    return el.tag.split("}")[-1]


def local_attrs(el) -> dict[str, str]:
    return {k.split("}")[-1]: v for k, v in el.attrib.items()}


def norm_text(s: str) -> str:
    """比对用：去掉空白。"""
    return re.sub(r"\s+", "", s or "")


FONT_ALIAS = {
    "simsun": "宋体", "宋体": "宋体", "nsimsun": "宋体",
    "simhei": "黑体", "黑体": "黑体",
    "fangsong": "仿宋", "仿宋": "仿宋", "simfang": "仿宋",
    "kaiti": "楷体", "楷体": "楷体", "simkai": "楷体",
    "microsoft yahei": "微软雅黑", "微软雅黑": "微软雅黑",
    "dengxian": "等线", "等线": "等线",
}


def canon_font(name) -> str:
    """字体名归一：SimSun 与 宋体 是同一款字，两边都归一才能比。

    取值层（own/wps）只报文档/WPS 原始给出的名字，归一在比对层做。
    """
    if not name:
        return ""
    s = str(name).strip()
    return FONT_ALIAS.get(s.lower(), s)


def first_family(name) -> str:
    return canon_font(name).split(",")[0].strip().strip('"').strip("'").lower()


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x3000 <= o <= 0x303F
        or 0xFF00 <= o <= 0xFFEF
    ) and ch.strip() != ""


def corpus() -> list[Path]:
    return sorted(p for p in CORPUS.glob("*.docx") if not p.name.startswith("~$"))


def write_json(path: Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def approx(x, y, tol: float = 0.15) -> bool:
    if x is None and y is None:
        return True
    if x is None or y is None:
        return False
    try:
        return abs(float(x) - float(y)) <= tol
    except (TypeError, ValueError):
        return x == y
