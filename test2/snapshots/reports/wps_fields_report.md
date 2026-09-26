# 域（field）与 TOC 域跨度 — WPS 真值对账报告

## 交付物

- 脚本：`test2/docxfmt/wps_fields.py`（容器内跑，只用 pywpsrpc + 标准库；未改动任何已有文件）
- 输出：`<outdir>/<stem>.wpsfields.json`，形状：

```json
{
  "path": "/in/xxx.docx",
  "tool": "wps",
  "counts": {"fields": 138, "by_code": {"PAGEREF": 60, "HYPERLINK": 60, "PAGE": 1}},
  "fields": [
    {"i": 1, "type": 58, "code": "PAGEREF",
     "code_text": " PAGEREF _Toc2273451 \\h ", "para": 120, "end_para": 120}
  ],
  "toc_spans": [{"code": "TOC", "para": 30, "end_para": 120}]
}
```

> 注意：规格里的示例 `PAGEREF → 58` 是示意；实测 **PAGEREF=37，58 是 EMBED**（见第 4 点）。
> `code_text` 按规格去首尾空白（示例里的空白只是说明“原样”，实际输出已 strip）。

## 怎么跑

```bash
cd test2
(cd corpus && ls -1 *.docx | sed 's|^|/in/|') > out/paths_fld.txt
docker run --rm --platform linux/amd64 \
  -v "$PWD/corpus:/in:ro" -v "$PWD/out:/out" \
  -v "$PWD/docxfmt/wps_fields.py:/opt/wps_fields.py:ro" \
  thesis-format-review/wps:dev \
  bash -lc "python3 /opt/wps_fields.py --outdir /out --list /out/paths_fld.txt"
```

校验脚本（对账 WPS 域列表 vs OOXML `w:fldChar`/`w:instrText`/`w:fldSimple`）：

```bash
cd test2 && uv run python out/verify_fields.py              # 全 40 篇
uv run python out/verify_fields.py 论文初稿 2206181072_李煜_...  # 单篇并打明细
```

临时探查脚本（都在 `out/`）：`probe_fields.py`、`probe_boundary.py`、`probe_shapes.py`、
`probe_para.py`、`probe_hf_fields.py`、`synth_field_probe.py`、`synth_shape_probe.py`、`verify_fields.py`。

## 实测结果摘要

- 全 40 篇：`wps_fields.py` 完成 **40/40**，`段落映射不到: 0`，`取不到的属性` 空。
- 域总数（`doc.Fields`）：**2793** 个。by_code：`HYPERLINK 1224 / PAGEREF 1194 / REF 174 /
  SEQ 74 / EMBED 61 / TOC 39 / SHAPE 15 / INCLUDEPICTURE 12`。
- 校验：**code 2793/2793、para 2793/2793、end_para 2793/2793 = 100.000%**。
  （OOXML 侧需把三类 WPS 合成域补上才能对齐：`w:object`→EMBED、正文 `w:hyperlink`→HYPERLINK、
  内联 legacy VML 文本框→SHAPE。39/40 篇只涉及 EMBED 这一项。）

## 六点结论

### 1) `Field.Code.Text` / `Field.Type` / `Field.Result.Start|End` 可用吗

有 **`Field.Range` 根本不存在**（`AttributeError: 'Field' object has no attribute 'Range'`）——
这是最关键一条。逐项实测：

| 属性 | 可用 | 备注 |
|---|---|---|
| `Field.Type` | ✅ | int |
| `Field.Code` | ✅ | Range |
| `Field.Code.Text` | ✅ | 域代码原文（未公开 `Data`） |
| `Field.Code.Start/End` | ✅ | 就是 `w:instrText` 那一段区间 |
| `Field.Result` | ✅ | Range |
| `Field.Result.Start/End` | ✅ | 域结果区间 |
| `Field.Range` | ❌ | **无此属性** |
| `Field.Index/Data/Kind/Locked/ShowCodes` | ✅ | 另有 `Next/Previous/Update/Unlink` |

因为 `Range` 取不到，脚本把「域跨度」定义为 **`Code.Start` 起、`Result.End` 止**
（`Field.Code` 是 `w:instrText`，`w:fldChar begin` 就在它前一个字符）。
`para` = 起点所在段，`end_para` = 终点所在段。段落 `Range` 相邻共享端点
（`p_j.End == p_{j+1}.Start`），所以末段落落点用 `End-1`，否则 TOC 的 `end_para` 会多 1。

### 2) 域→段落映射准不准

准。`out/verify_fields.py` 用与 `own.iter_paragraphs` 相同的「表格行末补占位段」口径把 OOXML
段落号对齐到 WPS 段落号，再逐个域比对：

```
域总数  WPS=2793  逐位对齐数=2793
code 一致     2793/2793 = 100.000%
para 一致     2793/2793 = 100.000%
end_para 一致 2793/2793 = 100.000%
```

三点必须注意（都是实测撞出来的）：

- **一个域的指令可能拆成多个 `w:instrText`**：要把 `begin→separate` 之间的 `instrText`
  按文档顺序拼起来才算一个域码（例：`main-text-paragraph` 37 个域 → 75 个 `instrText`）。
- **`w:fldChar` 不是 WPS 域的全部**。WPS 还会「合成」三类 OOXML 里没有域标记的域：
  - `w:object`（OLE 对象）→ **EMBED**（域码 `EMBED Equation.3`），实测 61 个；
  - 正文里的结构超链接 `w:hyperlink` → **HYPERLINK**（`论文2206181106` 里 121 个正文
    `w:hyperlink` ↔ 121 个 HYPERLINK 域，文本框内的 6 个不算）；
  - **内联 legacy VML 文本框**（`w:pict/v:shape/v:textbox`，样式非 `position:absolute`）
    → **SHAPE**（域码 `SHAPE  \* MERGEFORMAT`），实测 15 个，段落号与文本框锚点段完全一致。
- **`w:fldSimple` 语料里一个都没有**（40 篇全 0），所以那条分支只在合成样本上验证过：
  合成 `w:fldSimple instr=" PAGE "` 后 `doc.Fields.Count` 正好 +1（Type=33），WPS 认它。

`论文2206181106_王雨诺...` 是最极端的一篇：OOXML 里 `fldChar/instrText/fldSimple` **全为 0**，
但 WPS 报 136 个域（121 HYPERLINK + 15 SHAPE），全部是合成域。补上上述规则后 136/136 对齐。

### 3) 嵌套域与 TOC 跨度

- `doc.Fields` **会把嵌套域都列出来**：TOC 域在前，其结果的 HYPERLINK/PAGEREF 按文档顺序
  跟在后面。例 `论文初稿`：`i=1 TOC`，`i=2..48` 是 47 个 PAGEREF。
- **TOC 的跨度覆盖整个目录区**：`Code.Start`（目录 Begin 处）到 `Result.End`（最后一个条目末）。
  实测与 OOXML 的 `begin fldChar` 段 ~ 结果最后一字段对齐：
  `论文初稿 28..74`、`2206181072_李煜 41..100`、`main-text-paragraph 32..49`。
  注意 OOXML 的 `end fldChar` 常落在目录**后一段**（`论文初稿` 是 p75），所以校验时
  `end_para` 要取「结果最后一字的段落」而不是 `end fldChar` 所在段落。
- `论文2206181106` 没有 TOC 域，`toc_spans` 为空 `[]`（脚本对空安全）。

### 4) `code → type` 映射表（语料实测）

| code | `Field.Type` | 出现数 | 说明 |
|---|---:|---:|---|
| TOC | 13 | 39 | 目录 |
| PAGEREF | 37 | 1194 | 目录/交叉引用页码 |
| HYPERLINK | 88 | 1224 | 含结构超链接合成 |
| REF | 3 | 174 | 交叉引用 |
| INCLUDEPICTURE | 67 | 12 | 域标记写法 |
| SEQ | 12 | 74 | 图表编号 |
| EMBED | 58 | 61 | **来自 `w:object`**，代码 `EMBED Equation.3` |
| SHAPE | 95 | 15 | **来自内联 VML 文本框** |
| PAGE | 33 | — | **只在页眉页脚**，不在 `doc.Fields`（见第 5 点） |

以后判类型优先用这张表（或直接用 `code`，比 `type` 稳）。

### 5) 页眉页脚里的域

`doc.Fields` **只给正文**，页眉页脚里的 PAGE 域取不到，必须逐节单独取
`Sections.Item(k).Headers/Footers.Item(j).Range.Fields`。实测：

- `global-footer-page-number-format`：`doc.Fields=39`（正文，`PAGE` 计数 0）；
  `sec3..sec10` 的 `Footers(1)` 各 1 个 `PAGE`（合计 8）。
- `2206181072_李煜`：`doc.Fields=138`；`sec2..sec8` 的 `Footers(1)` 各 1 个 `PAGE`（合计 7）。

即「页码域数」不能用 `doc.Fields`，要按节取（这也与 `wps_pages.py` 的口径一致）。

### 6) 文本框里的域

- **`doc.Fields` 不算文本框内的域**。合成实验：往文本框里插一个 `PAGE` 域，`doc.Fields`
  只 +1（来自正文那个 `w:fldSimple`），文本框里那个没进；因为文本框的文本是**另一个 story**。
- 但它**可以**从形状对象取到：`doc.Shapes.Item(k).TextFrame.TextRange.Fields`。
  合成样本里直接文本框 Shape（Type=1）报 `Fields.Count=1`、`Code.Text=' PAGE \* MERGEFORMAT '`。
- 组合形状（Shape.Type=6，Group）的 `TextFrame.TextRange` 直接取会失败
  （`0x80000008`），需要下钻 `GroupItems`；`doc.InlineShapes` 的项**没有 `TextFrame`**。
- 另有一条 WPS 怪癖：**内联** legacy VML 文本框会让 WPS 在 `doc.Fields` 里合成一个
  **SHAPE(type=95)** 域（见第 2/4 点）；而浮动文本框（`position:absolute` 或 DrawingML
  `wp:anchor`）不算。合成对照实验：内联 VML 文本框 → `SHAPE=1`；浮动 VML 文本框 → `SHAPE=0`。
- 自研侧既定口径是「文本框不下钻」，与「`doc.Fields` 不算文本框内域」天然一致；
  要看文本框内域得单独走 `Shapes`。

## 踩到的怪癖（汇总）

1. **`Field.Range` 不存在**（MS Word 有，WPS 的 pywpsrpc 绑定没有）。只能用 `Code`/`Result`。
2. **段落 `Range.End` 落在下一段起点**，末段落落点必须 `End-1`。
3. **`doc.Fields` 把结构超链接、OLE 对象、内联 VML 文本框都算成域**，不能简单等同于
   `w:fldChar`。反过来，文本框**文字里**的域它又不算——两件事别混。
4. **TOC 的 `end fldChar` 在目录后一段**，`end_para` 要取结果最后一字的段落。
5. 一个域码可拆成多个 `w:instrText`，必须拼接。
6. `Range.Text` 的星形平面字符问题这里不涉及（域码/结果都短），但脚本沿用了防御式取值。
7. `HeaderFooter.Range.Fields` 报的是**本节生效后**的域（继承节也可能报 1 个 PAGE），
   与「只有本节自有时才比 PAGE 域数」的既有口径要区分开。
