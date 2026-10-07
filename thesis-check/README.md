# thesis-check

毕业论文格式自动审核。输入学生用 WPS 保存的 `.docx`，输出**逐条、可定位、可解释**的问题清单，
并以 Word 批注标进文档。

- 范围：第一批 197 条 + 第二批 7 条 + 目录缩进 3 条规则（共 207 条，见 [需求文档](../docs/chat/9.26/需求文档.md)）
- 实现：见 [技术设计](../docs/chat/9.26/技术设计.md)
- 判定依据：`docs/规则/*.md`（213 条规则的唯一权威来源）

## 三条命令

```bash
uv sync              # 装依赖（含 dev）
./scripts/check.sh   # 门禁：ruff + ty + 分层契约 + pytest
uv run thesis-check --version
```

跑一篇（M1 之前会如实告诉你"尚未实现"）：

```bash
uv run thesis-check 论文.docx -o out/
```

## 嵌入到 Web 服务

```python
from thesischeck.pipeline import review_bytes

payload = review_bytes(uploaded_bytes)  # 字节进、内存出，不写磁盘
payload.report.to_json()  # 问题清单（同 issues.json 的形状）
payload.marked_docx  # 标注版 docx 字节（供下载）
```

部署态（安装后的包没有 `.git`）用环境变量 `THESISCHECK_RULESET_VERSION` 注入规则集版本。

## 分层

只能自上而下依赖，由 [`.importlinter`](./.importlinter) 强制：

```
cli  →  pipeline  →  report  →  rules  →  index  →  semantics  →  parse  →  errors
```

| 层 | 干什么 | 不许干什么 |
|---|---|---|
| `parse` | 读 OOXML，产事实（含有效格式级联） | 出现任何判定逻辑 |
| `semantics` | 作用域分区、块角色、具名选择器 | 取属性值、判对错 |
| `index` | 收集跨篇事实（模块/章/图表/引用/目录条目） | 判定 |
| `rules` | 数据驱动判定 | **碰 XML**、硬编码段号 |
| `report` | 报告 + 批注写回 | 重新判定、改正文 |

两条铁律：**解析产事实、规则做判定**；**规则层不碰 XML**（加一条属性类规则应只有一行数据）。

## 语料

| 层 | 内容 | 进版本库 |
|---|---|---|
| 合成样张 / 学校材料 | 全合规底稿 + 偏差变体、规范样张 | ✅ |
| 真实论文 | 40 篇（脱敏、改名） | ❌ 用 `THESIS_CORPUS_DIR` 指 |
| 真值快照 | `test2/snapshots/`（gzip） | ✅ 用作解析器重写的等价性基线 |

## 开发期校准

WPS 只做**开发期校准**，生产与常规 CI 不依赖它：`test2/`（对账工程）+ `deploy/wps`（镜像）。
