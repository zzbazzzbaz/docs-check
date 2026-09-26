"""异常体系。

三条纪律（需求文档 NFR-3）：

1. **坏文件不崩**：`BadDocument` 要转成可读提示，不是堆栈。
2. **单条规则异常不中断整篇**：`RuleError` 记为该规则未执行，其余照跑。
3. **宽容解析要记账**：不认识的 XML 结构不抛异常，但必须进"未认识元素"清单，
   否则"没报"就等于"没查"。
"""


class ThesisCheckError(Exception):
    """本项目异常基类。"""


class BadDocument(ThesisCheckError):
    """输入本身的问题，面向用户：不是 docx / 加密 / 损坏 / 超限 / 带宏。"""


class ParseError(ThesisCheckError):
    """解析失败，附部件名与细节，便于定位。"""

    def __init__(self, part: str, detail: str) -> None:
        super().__init__(f"{part}: {detail}")
        self.part = part
        self.detail = detail


class RuleError(ThesisCheckError):
    """单条规则执行失败。捕获后记入报告"该规则未执行"，不中断整篇审核。"""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"{rule}: {detail}")
        self.rule = rule
        self.detail = detail
