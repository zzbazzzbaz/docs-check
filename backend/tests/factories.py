"""测试用 docx 字节工厂：手拼最小 OOXML。

不提交二进制样本、不依赖 `../thesis-check` 语料；坏文档路径单独提供。
"""

import io
import zipfile
from collections.abc import Sequence

_MAIN_DOC_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_OFFICE_DOC_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)

_CONTENT_TYPES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="{_MAIN_DOC_CONTENT_TYPE}"/>
</Types>
"""

_PACKAGE_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="{_OFFICE_DOC_REL_TYPE}" Target="word/document.xml"/>
</Relationships>
"""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _document_xml(paragraphs: Sequence[str]) -> str:
    body = "".join(f"<w:p><w:r><w:t>{_escape(text)}</w:t></w:r></w:p>" for text in paragraphs)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body>"
        "</w:document>"
    )


def make_docx(paragraphs: Sequence[str] = ("测试段落",)) -> bytes:
    """拼一个最小可解析的 .docx（[Content_Types].xml + 关系 + word/document.xml）。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _PACKAGE_RELS)
        archive.writestr("word/document.xml", _document_xml(paragraphs))
    return buffer.getvalue()


def minimal_docx_bytes() -> bytes:
    return make_docx()


def corrupt_docx_bytes() -> bytes:
    """不是 zip 的伪 docx（引擎应拒绝并给出中文原因）。"""
    return b"this is definitely not a docx file"
