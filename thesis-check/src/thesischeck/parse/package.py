"""L1 包层：打开 .docx（zip）并安全地读部件。

上传的文件是**不可信输入**（需求 NFR-2），所以这一层每条路径都要能**拒绝**而不是崩溃：

- XML 解析：禁外部实体、禁网络、禁 huge_tree（防 XXE 与"十亿笑"）
- zip 中央目录：条目数 / 解压总量 / 单部件大小 / 压缩比上限，拒绝路径穿越，拒绝加密条目
- 拒绝宏文档与老式 .doc，并给出**可读**原因（面向学生，不出现堆栈）
- 关系部件（rels）：只认包内部件；`TargetMode="External"` 的（超链接等）**跳过，不访问**

线程：一个 `Package` 实例只服务一篇文档、只被一个线程使用（`zipfile` 的文件句柄不是线程安全的）。
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self, cast

from lxml import etree

from ..errors import BadDocument, ParseError

PART_CONTENT_TYPES = "[Content_Types].xml"
PART_DOCUMENT = "word/document.xml"
PART_STYLES = "word/styles.xml"
PART_NUMBERING = "word/numbering.xml"
PART_SETTINGS = "word/settings.xml"
PART_THEME = "word/theme/theme1.xml"
PART_COMMENTS = "word/comments.xml"
MACRO_PART = "word/vbaProject.bin"

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_ENTRY_BYTES = 80 * 1024 * 1024
MAX_TOTAL_BYTES = 300 * 1024 * 1024
# 单部件元素数上限：50 MB 体积上限拦不住"结构摊薄"的病态文档（例如 50 MB 全是空段落）。
# lxml 在 50 MB 内解析只需数秒，这个上限只用于拒绝真正病态的形状，正常论文远低于此。
MAX_ELEMENTS = 2_000_000
MAX_COMPRESSION_RATIO = 200
RATIO_CHECK_ABOVE = 1 << 20  # 小于 1MB 的条目不查压缩比，避免误伤小部件

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class Relationship:
    """一条包内关系。`kind` 取类型 URI 的末段（header / footer / styles / image ...）。"""

    id: str
    kind: str
    target: str


def rels_part_name(part: str) -> str:
    """部件名 -> 它的关系部件名。`word/document.xml` -> `word/_rels/document.xml.rels`。"""
    head, _, tail = part.rpartition("/")
    return f"{head}/_rels/{tail}.rels" if head else f"_rels/{tail}.rels"


def resolve_target(part: str, target: str) -> str:
    """把关系里的目标（相对部件目录，或以 `/` 开头表示包根）归一成 zip 里的部件名。"""
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def parse_relationships(part: str, root: etree._Element | None) -> dict[str, Relationship]:
    """解析关系部件。纯函数，便于直接测。

    `TargetMode="External"` 的（超链接、外部图片等）**跳掉**：它们不是包内部件，我们也不去访问。
    """
    if root is None:
        return {}
    out: dict[str, Relationship] = {}
    for rel in root:
        if not isinstance(rel.tag, str) or not rel.tag.endswith("Relationship"):
            continue
        if rel.get("TargetMode") == "External":
            continue
        rid, target = rel.get("Id"), rel.get("Target")
        if not rid or not target:
            continue
        rtype = rel.get("Type") or ""
        out[rid] = Relationship(id=rid, kind=rtype.rsplit("/", 1)[-1], target=resolve_target(part, target))
    return out


def _new_parser() -> etree.XMLParser:
    """每次新建：lxml 的解析器实例不保证可并发复用。"""
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        collect_ids=False,
        remove_comments=False,
    )


def check_entries(entries: Sequence[zipfile.ZipInfo]) -> None:
    """检查 zip 中央目录。纯函数，便于逐条上限单独测。"""
    if len(entries) > MAX_ENTRIES:
        raise BadDocument(f"压缩包条目过多（{len(entries)}），不像正常的 Word 文档")

    total = 0
    for item in entries:
        name = item.filename
        if name.startswith("/") or _DRIVE.match(name) or ".." in name.split("/"):
            raise BadDocument(f"压缩包里含非法路径：{name}")
        if item.flag_bits & 0x1:
            raise BadDocument("文档已加密，无法审核；请另存为不加密的 .docx")
        if item.file_size > MAX_ENTRY_BYTES:
            raise BadDocument(f"文档内有超大部件（{name}，{item.file_size / 1048576:.0f} MB）")
        if item.file_size > RATIO_CHECK_ABOVE and item.compress_size > 0:
            ratio = item.file_size / item.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise BadDocument(f"压缩比异常（{name}，{ratio:.0f} 倍），疑似压缩炸弹")
        total += item.file_size

    if total > MAX_TOTAL_BYTES:
        raise BadDocument(f"文档解压后过大（{total / 1048576:.0f} MB）")


class Package:
    """一个已打开并校验过的 .docx。用 `with Package.open(path) as pkg:`。"""

    def __init__(self, path: Path, archive: zipfile.ZipFile) -> None:
        self.path = path
        self._zip = archive
        self._names = frozenset(archive.namelist())

    @classmethod
    def open(cls, path: str | Path) -> Self:
        target = Path(path)
        if not target.is_file():
            raise BadDocument(f"文件不存在：{target}")

        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            raise BadDocument(f"文件过大（{size / 1048576:.1f} MB），上限 {MAX_FILE_BYTES // 1048576} MB")

        with target.open("rb") as handle:
            if handle.read(8).startswith(_OLE_MAGIC):
                raise BadDocument("这是老式的 .doc 文件，请用 WPS 另存为 .docx 后再上传")

        try:
            archive = zipfile.ZipFile(target)
        except zipfile.BadZipFile as exc:
            raise BadDocument(f"不是有效的 .docx（不是 zip 包）：{exc}") from exc

        try:
            check_entries(archive.infolist())
            names = set(archive.namelist())
            if MACRO_PART in names:
                raise BadDocument("文档含宏，请另存为 .docx（不含宏）后再上传")
            if PART_DOCUMENT not in names or PART_CONTENT_TYPES not in names:
                raise BadDocument("这不是 Word 文档：缺少 word/document.xml")
        except Exception:
            archive.close()
            raise

        return cls(target, archive)

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def names(self) -> frozenset[str]:
        return self._names

    def has(self, name: str) -> bool:
        return name in self._names

    def relationships(self, part: str) -> dict[str, Relationship]:
        """某个部件的关系表：`r:id` -> Relationship。没有 rels 部件就是空表。"""
        return parse_relationships(part, self.xml(rels_part_name(part)))

    def read(self, name: str) -> bytes | None:
        """读一个部件；不存在返回 None（部件缺失是常见情况，不算错误）。"""
        try:
            raw = self._zip.read(name)
        except KeyError:
            return None
        except RuntimeError as exc:  # 加密条目在读取时才报
            raise BadDocument("文档已加密，无法审核") from exc
        if len(raw) > MAX_ENTRY_BYTES:
            # 中央目录里的 file_size 是文档自己声明的，可能撒谎；读出来的实际长度再拦一次
            raise BadDocument(f"部件过大（{name}）")
        return raw

    def xml(self, name: str) -> etree._Element | None:
        """读并解析一个 XML 部件；不存在返回 None，坏 XML 报可读错误。

        解析后统计元素总数，超 `MAX_ELEMENTS` 即拒绝——真正病态的文档防线（`NFR-2.4`）。
        """
        raw = self.read(name)
        if raw is None:
            return None
        try:
            root = etree.fromstring(raw, parser=_new_parser())
        except etree.XMLSyntaxError as exc:
            raise ParseError(name, f"XML 无法解析：{exc}") from exc
        if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
            raise BadDocument(f"文档结构过于庞大（{name} 元素数超出上限），无法审核")
        return cast(etree._Element, root)
