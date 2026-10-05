"""毕业论文格式自动审核。

分层（只能自上而下依赖，由 `.importlinter` 强制）：

    cli → pipeline → report → rules → index → semantics → parse → errors

两条铁律：

1. **解析产事实，规则做判定**——中间不做"半判定"。
2. **规则层不碰 XML**——加一条属性类规则应当只有一行数据。

设计与范围见 `docs/chat/9.26/需求文档.md` 与 `技术设计.md`。
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("thesischeck")
except PackageNotFoundError:  # 源码目录下直接跑（未安装）
    __version__ = "0.0.0+source"

__all__ = ["__version__"]
