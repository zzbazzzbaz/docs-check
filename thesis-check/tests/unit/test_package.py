"""包层：不可信输入的每一道防护都要有测试。

zip 的上限检查做成了纯函数 `check_entries`，可以直接把中央目录喂进去测——
比"构造一个真的加密/压缩炸弹压缩包"（标准库根本写不出来）可靠得多。
"""

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from thesischeck.errors import BadDocument, ParseError
from thesischeck.parse import package as pkg

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MIN_TYPES = b'<?xml version="1.0"?><Types/>'
MIN_DOC = (f'<?xml version="1.0"?><w:document xmlns:w="{W_NS}"><w:body/></w:document>').encode()


def entry(
    name: str,
    *,
    size: int = 10,
    compressed: int = 5,
    encrypted: bool = False,
) -> zipfile.ZipInfo:
    """造一个中央目录条目（只用于纯函数检查，不写实际数据）。"""
    info = zipfile.ZipInfo(name)
    info.file_size = size
    info.compress_size = compressed
    if encrypted:
        info.flag_bits |= 0x1
    return info


def make_docx(extra: dict[str, bytes] | None = None, *, document: bytes | None = MIN_DOC) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(pkg.PART_CONTENT_TYPES, MIN_TYPES)
        if document is not None:
            archive.writestr(pkg.PART_DOCUMENT, document)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buf.getvalue()


def write(tmp_path: Path, data: bytes, name: str = "thesis.docx") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ── 正常路径 ─────────────────────────────────────────────────────


def test_opens_minimal_document_and_reads_parts(tmp_path: Path) -> None:
    with pkg.Package.open(write(tmp_path, make_docx())) as doc:
        assert doc.read(pkg.PART_DOCUMENT) == MIN_DOC
        assert doc.has(pkg.PART_CONTENT_TYPES)
        root = doc.xml(pkg.PART_DOCUMENT)
        assert root is not None
        assert root.tag.endswith("document")


def test_missing_part_returns_none(tmp_path: Path) -> None:
    """部件缺失是常态（很多文档没有 numbering.xml），不算错误。"""
    with pkg.Package.open(write(tmp_path, make_docx())) as doc:
        assert doc.read(pkg.PART_NUMBERING) is None
        assert doc.xml(pkg.PART_STYLES) is None


# ── 关系部件（rels）─────────────────────────────────────────────

RELS = b"""<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://x/header" Target="header1.xml"/>
  <Relationship Id="rId2" Type="http://x/image" Target="media/image1.png"/>
  <Relationship Id="rId3" Type="http://x/hyperlink" Target="https://example.com/a" TargetMode="External"/>
  <Relationship Id="rId4" Type="http://x/footer" Target="/word/footer1.xml"/>
  <Relationship Id="rId5" Type="http://x/customXml" Target="../customXml/item1.xml"/>
</Relationships>"""


def test_rels_part_name() -> None:
    assert pkg.rels_part_name(pkg.PART_DOCUMENT) == "word/_rels/document.xml.rels"
    assert pkg.rels_part_name("document.xml") == "_rels/document.xml.rels"


def test_relationship_targets_are_normalised(tmp_path: Path) -> None:
    """目标相对部件目录；`/` 开头是包根；`../` 要能回到上层。"""
    data = make_docx({"word/_rels/document.xml.rels": RELS})
    with pkg.Package.open(write(tmp_path, data)) as doc:
        rels = doc.relationships(pkg.PART_DOCUMENT)
        assert rels["rId1"].target == "word/header1.xml"
        assert rels["rId1"].kind == "header"
        assert rels["rId2"].target == "word/media/image1.png"
        assert rels["rId4"].target == "word/footer1.xml"
        assert rels["rId5"].target == "customXml/item1.xml"


def test_external_relationships_are_skipped(tmp_path: Path) -> None:
    """超链接之类的外部目标不是包内部件，跳过（我们也不去访问）。"""
    data = make_docx({"word/_rels/document.xml.rels": RELS})
    with pkg.Package.open(write(tmp_path, data)) as doc:
        assert "rId3" not in doc.relationships(pkg.PART_DOCUMENT)


def test_missing_rels_is_empty_table(tmp_path: Path) -> None:
    with pkg.Package.open(write(tmp_path, make_docx())) as doc:
        assert doc.relationships(pkg.PART_DOCUMENT) == {}


# ── 拒绝：文件级 ─────────────────────────────────────────────────


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(BadDocument, match="不存在"):
        pkg.Package.open(tmp_path / "nope.docx")


def test_non_zip_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(BadDocument, match="zip"):
        pkg.Package.open(write(tmp_path, b"this is not a zip at all"))


def test_old_doc_is_rejected_with_readable_reason(tmp_path: Path) -> None:
    """老式 .doc 是 OLE 复合文档，报错要说人话（提示另存为 .docx）。"""
    with pytest.raises(BadDocument, match=r"\.doc"):
        pkg.Package.open(write(tmp_path, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64))


def test_oversized_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pkg, "MAX_FILE_BYTES", 64)
    with pytest.raises(BadDocument, match="过大"):
        pkg.Package.open(write(tmp_path, make_docx() + b"\x00" * 200))


def test_macro_document_is_rejected(tmp_path: Path) -> None:
    data = make_docx({pkg.MACRO_PART: b"\x00" * 16})
    with pytest.raises(BadDocument, match="宏"):
        pkg.Package.open(write(tmp_path, data))


def test_missing_document_part_is_rejected(tmp_path: Path) -> None:
    data = make_docx(document=None)
    with pytest.raises(BadDocument, match="Word"):
        pkg.Package.open(write(tmp_path, data))


# ── 拒绝：中央目录上限（纯函数）─────────────────────────────────


def test_too_many_entries() -> None:
    entries = [entry("word/x.xml") for _ in range(pkg.MAX_ENTRIES + 1)]
    with pytest.raises(BadDocument, match="条目过多"):
        pkg.check_entries(entries)


@pytest.mark.parametrize(
    "name",
    ["/absolute/path.xml", "word/../../etc/passwd", "C:/windows/x.xml"],
)
def test_traversal_and_absolute_paths(name: str) -> None:
    with pytest.raises(BadDocument, match="非法路径"):
        pkg.check_entries([entry(name)])


def test_encrypted_entry() -> None:
    with pytest.raises(BadDocument, match="加密"):
        pkg.check_entries([entry("word/document.xml", encrypted=True)])


def test_compression_bomb_ratio() -> None:
    """尺寸在上限内，但压缩比异常 -> 压缩炸弹。

    注意别让用例越过单部件上限，否则先撞的是"超大部件"，测不到这条路径。
    """
    size = 4 * 1024 * 1024
    assert size < pkg.MAX_ENTRY_BYTES
    boom = entry("word/document.xml", size=size, compressed=1024)
    with pytest.raises(BadDocument, match="压缩比"):
        pkg.check_entries([boom])


def test_small_entries_are_not_ratio_checked() -> None:
    """小于 1MB 的条目不查压缩比，避免误伤（小部件压缩比天然高）。"""
    pkg.check_entries([entry("word/styles.xml", size=4096, compressed=8)])


def test_total_uncompressed_size() -> None:
    each = pkg.MAX_TOTAL_BYTES // 4 + 1
    entries = [entry(f"word/part{i}.xml", size=each, compressed=each) for i in range(4)]
    with pytest.raises(BadDocument, match="解压后过大"):
        pkg.check_entries(entries)


def test_oversized_single_entry() -> None:
    big = entry("word/media/image1.png", size=pkg.MAX_ENTRY_BYTES + 1, compressed=pkg.MAX_ENTRY_BYTES // 100)
    with pytest.raises(BadDocument, match="超大部件"):
        pkg.check_entries([big])


# ── XML 解析防护 ─────────────────────────────────────────────────


def test_internal_entities_are_not_expanded(tmp_path: Path) -> None:
    """十亿笑：实体不展开，解析立刻返回（展开会挂死）。"""
    doc = f"""<?xml version="1.0"?>
<!DOCTYPE w:document [
  <!ENTITY lol "hahaha">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>&lol2;</w:t></w:r></w:p></w:body></w:document>
""".encode()
    with pkg.Package.open(write(tmp_path, make_docx(document=doc))) as opened:
        root = opened.xml(pkg.PART_DOCUMENT)
        assert root is not None
        assert b"hahaha" not in etree.tostring(root)


def test_billion_laughs_is_rejected(tmp_path: Path) -> None:
    """经典十亿笑：9 层实体，展开是 10^10 个字符。

    实测 libxml2 自带"实体放大系数"上限，**直接拒绝解析**——比"不展开"更强。
    断言两件事：报的是可读错误（带部件名），且**立刻返回**；
    防护一旦失效，这个测试会挂死或被内存杀掉。
    """
    entities = ['<!ENTITY lol0 "lol">']
    for level in range(1, 10):
        expanded = ("&lol" + str(level - 1) + ";") * 10
        entities.append(f'<!ENTITY lol{level} "{expanded}">')
    doc = (
        '<?xml version="1.0"?>\n<!DOCTYPE w:document [\n  '
        + "\n  ".join(entities)
        + f'\n]>\n<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>&lol9;</w:t></w:r></w:p>'
        + "</w:body></w:document>"
    ).encode()

    with (
        pkg.Package.open(write(tmp_path, make_docx(document=doc))) as opened,
        pytest.raises(ParseError, match=r"document\.xml"),
    ):
        opened.xml(pkg.PART_DOCUMENT)


def test_external_entities_are_not_read(tmp_path: Path) -> None:
    """XXE：不读本地文件、不联网。"""
    doc = f"""<?xml version="1.0"?>
<!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body></w:document>
""".encode()
    with pkg.Package.open(write(tmp_path, make_docx(document=doc))) as opened:
        root = opened.xml(pkg.PART_DOCUMENT)
        assert root is not None
        assert b"root:" not in etree.tostring(root)


def test_broken_xml_gives_readable_error(tmp_path: Path) -> None:
    data = make_docx(document=b"<w:document><unclosed>")
    with (
        pkg.Package.open(write(tmp_path, data)) as doc,
        pytest.raises(ParseError, match="XML 无法解析"),
    ):
        doc.xml(pkg.PART_DOCUMENT)


def test_too_many_elements_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """病态文档防线（`NFR-2.4`）：元素总数超上限即拒绝，替代在线程池里不可靠的墙钟超时。"""
    monkeypatch.setattr(pkg, "MAX_ELEMENTS", 3)
    document = (
        f'<?xml version="1.0"?><w:document xmlns:w="{W_NS}"><w:body><w:p/><w:p/><w:p/></w:body></w:document>'
    ).encode()
    with (
        pkg.Package.open(write(tmp_path, make_docx(document=document))) as doc,
        pytest.raises(BadDocument, match="元素"),
    ):
        doc.xml(pkg.PART_DOCUMENT)
