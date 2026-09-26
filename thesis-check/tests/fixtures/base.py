"""全合规底稿生成器：**程序化拼**一份最小但完整的论文 docx。

为什么生成而不是提交二进制（技术设计 §9.2）：底稿要能评审、能 diff；二进制进 git
既看不清改了什么，也会随 WPS 版本漂移。生成一份全合规论文的成本远低于清洗学校样张。

覆盖的对象种类（用于规则测试的对象选择器都能在底稿里找到目标）：

- 8 个模块：封面 / 中文摘要 / 英文摘要 / 目录 / 正文 / 参考文献 / 致谢 / 附录
- 各级标题：一级（`第X章`）、二级（`N.N`）、三级（`N.N.N`）、三级以下（`（1）`）
- 正文段、图（`w:drawing`）、图题、表 + 表题（三线表）、公式段 + 公式编号
- 文献条目、附录子标题、中文 / 英文关键词行
- 页眉、页脚（PAGE 域）、分节（3 节，含页眉继承）、页面设置（A4 + 页边距 + 页码形式）
- 目录标题 + `TOC` 域（跨段的 begin/end）+ `toc 1/2/3` 条目

本阶段只有一条示范规则，底稿对它是零问题。**真正零问题要等批 1 规则写完后再迭代**，
这是预期（Phase 7 只交付引擎与脚手架）。
"""

from __future__ import annotations

import io
import zipfile
from functools import lru_cache

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"

DOCUMENT = "word/document.xml"
STYLES = "word/styles.xml"
HEADER = "word/header1.xml"
FOOTER = "word/footer1.xml"
DOC_RELS = "word/_rels/document.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"

# A4：11906 x 16838 twips；页边距上下左右 2.6cm（1474 缇）
_A4 = '<w:pgSz w:w="11906" w:h="16838"/>'
_PGMAR = (
    '<w:pgMar w:top="1474" w:bottom="1474" w:left="1474" w:right="1474"'
    ' w:header="851" w:footer="992" w:gutter="0"/>'
)


def run(
    text: str,
    *,
    ea: str | None = None,
    west: str | None = None,
    size: float | None = None,
    bold: bool = False,
    va: str | None = None,
) -> str:
    """一个 run；只写显式属性，其余走 styles.xml 的级联。"""
    parts: list[str] = []
    if ea is not None or west is not None:
        fonts = ""
        if west is not None:
            fonts += f' w:ascii="{west}" w:hAnsi="{west}"'
        if ea is not None:
            fonts += f' w:eastAsia="{ea}"'
        parts.append(f"<w:rFonts{fonts}/>")
    if bold:
        parts.append("<w:b/>")
    if size is not None:
        parts.append(f'<w:sz w:val="{int(size * 2)}"/>')
    if va is not None:
        parts.append(f'<w:vertAlign w:val="{va}"/>')
    rpr = f"<w:rPr>{''.join(parts)}</w:rPr>" if parts else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def para(
    inner: str = "",
    *,
    style: str | None = None,
    outline: int | None = None,
    align: str | None = None,
    line: float | None = None,
    first_line_chars: float | None = None,
    page_break_before: bool = False,
) -> str:
    props: list[str] = []
    if style is not None:
        props.append(f'<w:pStyle w:val="{style}"/>')
    if outline is not None:
        props.append(f'<w:outlineLvl w:val="{outline}"/>')
    if align is not None:
        props.append(f'<w:jc w:val="{align}"/>')
    if line is not None:
        props.append(f'<w:spacing w:line="{int(line * 240)}" w:lineRule="auto"/>')
    if first_line_chars is not None:
        props.append(f'<w:ind w:firstLineChars="{int(first_line_chars * 100)}"/>')
    if page_break_before:
        props.append("<w:pageBreakBefore/>")
    ppr = f"<w:pPr>{''.join(props)}</w:pPr>" if props else ""
    return f"<w:p>{ppr}{inner}</w:p>"


def _sect_break(sect_pr: str) -> str:
    return f"<w:p><w:pPr><w:sectPr>{sect_pr}</w:sectPr></w:pPr></w:p>"


def _module_title_line(text: str, *, bold: bool = False) -> str:
    return para(run(text, ea="黑体", size=16, bold=bold), align="center", line=1.5)


def _body_line(text: str, *, indent: bool = True) -> str:
    return para(
        run(text, ea="宋体", west="Times New Roman", size=12),
        line=1.5,
        first_line_chars=2 if indent else None,
    )


def _cover() -> str:
    lines = [
        # 样张该行末尾有一个空的 42pt run，用于验证 COV-02 忽略空 run
        para(
            run("本科生毕业设计（论文）", ea="方正小标宋简体", size=36)
            + run("", ea="方正小标宋简体", size=42),
            align="center",
        ),
        para(
            run("题    目：", ea="仿宋", size=16, bold=True)
            + run("基于嵌入式系统的智能监测装置", ea="黑体", size=18),
            align="center",
        ),
        para(run("学生姓名：张三", ea="仿宋", size=16, bold=True), align="center"),
        para(run("学    号：2026000001", ea="仿宋", size=16, bold=True), align="center"),
        para(run("院    系：信息科学与工程学院", ea="仿宋", size=16, bold=True), align="center"),
        para(run("专业年级：电子信息工程2022级", ea="仿宋", size=16, bold=True), align="center"),
        para(run("指导教师：李四", ea="仿宋", size=16, bold=True), align="center"),
        para(run("2026 年 6 月 1 日", ea="仿宋", size=16, bold=True), align="center"),
    ]
    return "".join(lines)


def _chinese_abstract() -> str:
    return "".join(
        [
            _module_title_line("摘    要"),
            para(),  # 标题后 1 个空段
            _body_line("本设计针对ARM嵌入式场景下的实时监测需求，给出了一套软硬件协同方案。"),
            _body_line("测试表明该方案满足精度与实时性要求，具有一定应用价值。"),
            para(),  # 正文后 1 个空段
            para(
                run("关键词：", ea="宋体", size=12, bold=True)
                + run("嵌入式系统；ARM；实时性", ea="宋体", west="Times New Roman", size=12),
                line=1.5,
                first_line_chars=2,
                align="both",
            ),
        ]
    )


def _english_abstract() -> str:
    return "".join(
        [
            _module_title_line("ABSTRACT", bold=True),
            para(),
            _body_line(
                "This design addresses real-time monitoring in embedded scenarios with a "
                "hardware-software scheme."
            ),
            para(),
            para(
                run("Keywords：", west="Times New Roman", size=12, bold=True)
                + run("embedded system；monitoring；real time", west="Times New Roman", size=12),
                line=1.5,
                first_line_chars=2,
                align="both",
            ),
        ]
    )


def _field_begin(code: str) -> str:
    return (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> {code} </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r></w:p>'
    )


def _field_end() -> str:
    return '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'


def _table_of_contents() -> str:
    # 一级条目（第X章型）编号后空 2 格；二 / 三级条目空 1 格
    entries = [
        ("第一章  绪论", "TOC1"),
        ("1.1 研究背景与意义", "TOC2"),
        ("1.1.1 国内研究现状", "TOC3"),
        ("参考文献", "TOC1"),
        ("致    谢", "TOC1"),
        ("附    录", "TOC1"),
    ]
    body = "".join(
        para(run(text, ea="宋体", west="Times New Roman", size=12), style=style, line=1.5)
        for text, style in entries
    )
    return _module_title_line("目    录") + _field_begin('TOC \\o "1-3" \\h \\z \\u') + body + _field_end()


def _cell(inner: str) -> str:
    return f"<w:tc><w:tcPr/>{para(inner)}</w:tc>"


def _cell_text(text: str) -> str:
    return _cell(run(text, ea="宋体", west="Times New Roman", size=12))


def _three_line_table() -> str:
    borders = (
        '<w:tblBorders><w:top w:val="single"/>'
        '<w:bottom w:val="single"/><w:insideH w:val="single"/>'
        '<w:left w:val="none"/><w:right w:val="none"/><w:insideV w:val="none"/>'
        "</w:tblBorders>"
    )
    rows = [
        [_cell_text("表头一"), _cell_text("表头二")],
        # 「数据一」格带一个上标引用，覆盖表格里的引用标注（TXT-30/31）
        [
            _cell(
                run("数据一", ea="宋体", west="Times New Roman", size=12)
                + run("[2]", west="Times New Roman", size=12, va="superscript")
            ),
            _cell_text("数据二"),
        ],
    ]
    cells = "".join("<w:tr>" + "".join(row) + "</w:tr>" for row in rows)
    return f"<w:tbl><w:tblPr>{borders}</w:tblPr>{cells}</w:tbl>"


_CN_CHAPTERS = "〇一二三四五"


def _chapter(number: int, title: str, *, with_objects: bool) -> str:
    head = para(
        run(f"第{_CN_CHAPTERS[number]}章  {title}", ea="黑体", size=16),
        outline=0,
        align="center",
        line=1.5,
        page_break_before=number >= 2,  # 第一章另起一页归 GLB-22，本处只管第二~五章
    )
    sub = para(run(f"{number}.1 研究背景", ea="黑体", size=14), outline=1, line=1.5)
    subsub = para(
        run(f"{number}.1.1 现状分析", ea="黑体", size=12),
        outline=2,
        line=1.5,
        first_line_chars=2,
    )
    sub3 = para(run("（1）关键技术", ea="宋体", size=12), outline=3, line=1.5, first_line_chars=2)
    body = _body_line(f"这是第{number}章的正文段落，用于承载正文属性的判定对象。")
    parts = [head, para(), sub, subsub, sub3, body]
    if with_objects:
        parts += [
            para("<w:r><w:drawing><wp:inline/></w:drawing></w:r>", align="center"),
            para(run("图1-1 系统总体结构", ea="宋体", size=10.5), align="center"),
            para(run("表1-1 主要器件清单", ea="宋体", size=10.5), align="center"),
            _three_line_table(),
            para(
                "<w:r><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:r>"
                + run("(1-1)", ea="宋体", west="Times New Roman", size=10.5),
                align="center",
            ),
            _body_line(
                "该结论与已有研究一致" + run("[1]", west="Times New Roman", size=12, va="superscript") + "。",
                indent=True,
            ),
        ]
    return "".join(parts)


def _body() -> str:
    titles = ["绪论", "系统需求分析", "系统设计", "系统实现", "系统测试"]
    return "".join(_chapter(i, title, with_objects=(i == 1)) for i, title in enumerate(titles, 1))


def _references() -> str:
    items = [
        "[1] 严蔚敏，吴伟民.数据结构[M].北京：清华大学出版社，1997：35-37.",
        "[2] 王伟国，刘永萍，王生年，等.B/S模式网上考试系统分析与设计[J]."
        "石河子大学学报：自然科学版，2003，6(2)：145-147.",
    ]
    return (
        _module_title_line("参考文献")
        + para()  # 标题后 1 个空段
        + "".join(_body_line(item, indent=False) for item in items)
    )


def _acknowledgements() -> str:
    return (
        _module_title_line("致    谢")
        + para()  # 标题后 1 个空段
        + _body_line("感谢导师与同学在ESP32课题研究中给予的帮助。")
        + _body_line("感谢家人一直以来的支持。")
    )


def _appendix() -> str:
    return "".join(
        [
            _module_title_line("附    录"),
            para(),  # 标题后 1 个空段
            para(
                run("附录A 名词术语及缩略词", ea="黑体", west="Times New Roman", size=14),
                outline=1,
                line=1.5,
            ),
            _body_line("论文的附录用大写字母 A、B、C 依次编号。"),
            para(
                run("附录B 程序代码", ea="黑体", west="Times New Roman", size=14),
                outline=1,
                line=1.5,
            ),
            _body_line("此处为程序代码清单。"),
        ]
    )


def _styles_xml() -> str:
    fonts = (
        '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/><w:sz w:val="24"/>'
    )
    styles = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{n}">'
        f'<w:name w:val="heading {n}"/><w:pPr><w:outlineLvl w:val="{n - 1}"/></w:pPr></w:style>'
        for n in (1, 2, 3, 4)
    )
    toc = "".join(
        f'<w:style w:type="paragraph" w:styleId="TOC{n}"><w:name w:val="toc {n}"/></w:style>'
        for n in (1, 2, 3)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{W}">'
        f"<w:docDefaults><w:rPrDefault><w:rPr>{fonts}</w:rPr></w:rPrDefault></w:docDefaults>"
        f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        f'<w:name w:val="正文"/><w:pPr><w:jc w:val="both"/></w:pPr><w:rPr>{fonts}</w:rPr></w:style>'
        f"{styles}{toc}</w:styles>"
    )


def _header_xml() -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><w:hdr xmlns:w="{W}">'
        + para(run("山东石油化工学院本科毕业设计（论文）", ea="黑体", size=10.5), align="center")
        + "</w:hdr>"
    )


def _footer_xml() -> str:
    # PAGE 域：begin / instrText / separate / 结果 / end，5 个 run 都带五号字号
    rpr = '<w:rPr><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr>'
    field = (
        f'<w:r>{rpr}<w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r>{rpr}<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        f'<w:r>{rpr}<w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r>{rpr}<w:t>1</w:t></w:r>"
        f'<w:r>{rpr}<w:fldChar w:fldCharType="end"/></w:r>'
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><w:ftr xmlns:w="{W}">'
        + para(field, align="center")
        + "</w:ftr>"
    )


def _document_xml() -> str:
    # 8 节，每模块一节：封面 / 中文摘要 / 英文摘要 / 目录 / 正文 / 参考文献 / 致谢 / 附录。
    # 页眉由节 2 引用，3~8 继承；页脚（PAGE）由节 5 引用，6~8 继承；封面与摘要、目录无页码。
    _hdr = '<w:headerReference w:type="default" r:id="rIdH1"/>'
    _ftr = '<w:footerReference w:type="default" r:id="rIdF1"/>'
    body = (
        _cover()
        + _sect_break(_A4 + _PGMAR)
        + _chinese_abstract()
        + _sect_break(_A4 + _PGMAR + _hdr)
        + _english_abstract()
        + _sect_break(_A4 + _PGMAR)
        + _table_of_contents()
        + _sect_break(_A4 + _PGMAR)
        + _body()
        + _sect_break(_A4 + _PGMAR + _ftr + '<w:pgNumType w:fmt="decimal"/>')
        + _references()
        + _sect_break(_A4 + _PGMAR)
        + _acknowledgements()
        + _sect_break(_A4 + _PGMAR)
        + _appendix()
        + f"<w:sectPr>{_A4 + _PGMAR}</w:sectPr>"
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W}" xmlns:m="{M}" xmlns:wp="{WP}" xmlns:r="{R}">'
        f"<w:body>{body}</w:body></w:document>"
    )


def _relationships() -> str:
    rels = (
        '<Relationship Id="rIdH1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
        'Target="header1.xml"/>'
        '<Relationship Id="rIdF1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
        'Target="footer1.xml"/>'
        '<Relationship Id="rIdS1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{RELS}">{rels}</Relationships>'


@lru_cache(maxsize=1)
def base_docx() -> bytes:
    """生成全合规底稿的字节；进程内只生成一次。"""
    parts = {
        CONTENT_TYPES: '<?xml version="1.0" encoding="UTF-8"?><Types/>',
        DOCUMENT: _document_xml(),
        STYLES: _styles_xml(),
        DOC_RELS: _relationships(),
        HEADER: _header_xml(),
        FOOTER: _footer_xml(),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content.encode("utf-8"))
    return buffer.getvalue()


BASE = base_docx()
