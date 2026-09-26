# 文本框内容在 WPS 侧的真值 — 实施报告

## 脚本

| 文件 | 说明 |
|---|---|
| `docxfmt/wps_textbox.py` | 主脚本（容器内跑），产出 `<outdir>/<stem>.wpstextbox.json` |
| `out/verify_textbox.py` | 对账脚本（本地跑），把 WPS 结果与 OOXML `w:txbxContent` 直接解析比 |
| `out/probe_textbox*.py`、`out/synth_textbox.py` | 现场探查 / 合成验证，均一次性 |

## 怎么跑

```bash
cd test2
(cd corpus && ls -1 *.docx | sed 's|^|/in/|') > out/paths_tb.txt
docker run --rm --platform linux/amd64 \
  -v "$PWD/corpus:/in:ro" -v "$PWD/out:/out" \
  -v "$PWD/docxfmt/wps_textbox.py:/opt/wps_textbox.py:ro" \
  thesis-format-review/wps:dev \
  bash -lc "python3 /opt/wps_textbox.py --outdir /out --list /out/paths_tb.txt"

uv run --quiet python out/verify_textbox.py        # 对账
```

## 实测结果摘要（全 40 篇 + 1 篇合成验证）

- 语料里**只有 2 篇有文本框**：`校园便利店饮料补货周期优化研究`（1 个，DrawingML 浮动）、
  `论文2206181106_王雨诺… - 副本`（15 个，VML，其中 3 个在组合形状里）。
- 自研侧 `w:txbxContent` 全语料 **17 个**，去重后是 **16 个对象**：校园那 1 个是
  `mc:AlternateContent` 把同一个对象写成 DrawingML(`wps:txbx`) + VML(`v:textbox`) 两份。
- WPS 取到 **16 框**（1 + 15），与 OOXML 去重回退后的框数逐篇相等。
- 逐框对账（`out/verify_textbox.py`，含 1 篇合成文档共 21 框）：

  | 字段 | 一致率 |
  |---|---|
  | 框数（逐篇） | 41 / 41 = 100% |
  | 段数（逐框） | 21 / 21 = 100% |
  | 文本（逐框，拼接） | 21 / 21 = 100% |
  | 字号（逐段） | 64 / 64 = 100% |
  | `anchor_para`（逐框） | 21 / 21 = 100% |

  不一致清单：**0 条**。

## 输出文件

`<outdir>/<stem>.wpstextbox.json`。要求的字段都在；**额外加了 3 项**（便于 GLB-28，见第 6 点）：
`fields[].type`、`paragraphs[].list_type`、`paragraphs[].list_string`。
`align` 按示例给 WPS 原始 `Alignment` 枚举整数。

```json
{
  "path": "/in/xxx.docx", "tool": "wps",
  "counts": {"boxes": 3, "boxes_with_text": 2, "boxes_with_fields": 1},
  "boxes": [
    {"i": 1, "kind": "shape", "shape_type": 17, "anchor_para": 12,
     "text": "……",
     "fields": [{"code": "SEQ", "code_text": " SEQ 图 \\* ARABIC ", "type": 12}],
     "paragraphs": [{"text": "……", "font_ea": "SimSun", "font_ascii": "Times New Roman",
                     "size": 10.5, "align": 1, "list_type": 0, "list_string": null}]}
  ]
}
```

## 七点结论

### 1）`Shape.TextFrame` 能取到什么（逐个试）

| 取什么 | 结果 |
|---|---|
| `TextFrame.HasText` | ✅ `-1` 真 / `0` 假（空文本框也是 `-1`） |
| `TextFrame.TextRange` | ✅（但 `HasText=0` 时取会报 `0x80000008`） |
| `TextFrame.ContainingRange` / `MarginLeft/Right/Top/Bottom` / `WordWrap` / `AutoSize` | ✅（本任务不用） |
| `TextRange.Text` | ✅（含段落间 `\r`） |
| `TextRange.Font.Name / NameFarEast / NameAscii / Size / Bold / Italic / Underline` | ✅ 单段可用；**整段混合格式时不可靠**：`Size=9999999`(wdUndefined)、`Name=None` |
| `TextRange.Paragraphs`（`Count`、`Item(k).Range.Text`、`Item(k).Range.Characters`、`Item(k).Format.Alignment`） | ✅ |
| `TextRange.Characters`（`Item(k).Text`、`Item(k).Font.*`） | ✅ |
| `TextRange.Fields`（`Count`、`Item(k).Code.Text`、`Item(k).Type`） | ✅ |
| `TextRange.ListFormat.ListType / ListString / ListLevelNumber` | ✅（逐段用） |
| `TextRange.Start / End` | ✅，但**是另一个故事区的坐标**，不能映射正文段落 |
| `Paragraph.Style` | ❌ 仍是裸 `IDispatch`（已知，取不到样式名） |

结论：字体/字号必须**逐段**（或逐字符）取，照抄 `wps.py` 的 `scan_chars/_sample`；整段 `TextRange.Font` 只能用来看单一格式的框。

### 2）组合形状 `Shape.Type == 6`

- 组自身的 `TextRange` 会报 `0x80000008`（组里含无文本子形状时）。
- **可用递归做法**：`Type==6` → 取 `GroupItems.Count` / `GroupItems.Item(k)` → 递归；
  叶子形状只有当 `TextFrame.HasText` 为真时才取 `TextRange`（否则连接符/FreeForm 会报 `0x80000008`）。
- 实测：王雨诺 box 8/10/12 就是组合里的文本框（`Type=17` 在 `Type=6` 内），
  组合与其子形状 **`Anchor.Start` 相同**，所以 `anchor_para` 一致。
- 组合本身不产框，只产叶子。嵌套组合会自然递归（语料没有，合成没造）。

### 3）`InlineShapes` 有没有 `TextFrame`

**没有**（`AttributeError: 'InlineShape' object has no attribute 'TextFrame'`）。
更关键：即使 OOXML 是 `wp:inline` 的 DrawingML 文本框，WPS 也把它当 **`Shapes`**（`Type=17`），
不是 `InlineShape`。所以语料 + 合成验证下来，**内联文本框的内容只能从 `Shapes` 取**，
`InlineShapes` 里取不到任何文本框内容（脚本仍做了 guarded 尝试，恒跳过）。

### 4）`anchor_para` 的映射

- 用 **`Shape.Anchor.Start`**（组合内子形状同样有 `Anchor`，且与组相同）。
- 映射口径沿用 `wps_fields.py`：`Anchor.Start` 落在哪一段 `[Range.Start, Range.End)` 就是哪一段。
- **不要用 `TextRange.Start/End`**：它在另一个故事区（王雨诺 box1：`TextRange` 45482..45492
  而 `Anchor`=25049），与正文段落号对不上。
- OOXML 侧：框外层最近的 `w:p`，在 `iter_paragraphs`（+ 每个 `w:tr` 行末占位）序列里的下标 +1。
- 逐框一致率 **21/21 = 100%**（语料 16/16；`anchor_para` 映射不到 0）。

### 5）与 OOXML 逐框对账

`out/verify_textbox.py`：OOXML 的框 = `w:txbxContent` 且**不在 `mc:Fallback` 里**；
按 anchor 分组配对后比段数 / 文本 / 字号，另用「按文本配对」独立核对 anchor。
结果：框数 41/41 篇、段数 21/21 框、文本 21/21 框、字号 64/64 段、anchor 21/21 框，**全 100%，0 不一致**。
（一个有 16 个 `w:p` 的代码文本框、一个有 22 个 `w:p` 的文本框都逐段对上。）

### 6）`GLB-28`（文本框里的自动编号）能不能做 —— **能做**

- 有信号：**逐段** `para.Range.ListFormat.ListType`。`0` = 无编号，非 0 = 有编号；
  另可拿 `ListString`（渲染出的编号串）与 `ListLevelNumber`。
- 合成验证（`out/synth-inline-dml.docx`，在 `txbxContent` 段落写 `numPr`）：
  - `numId=1` → `ListType=3`、`ListString='第三章'`
  - `numId=0`（OOXML 口径的「取消编号」）→ `ListType=0`（与 README 一致）
  - 不写 → `0`
- **注意**：整段 `TextRange.ListFormat.ListType` 是混合值（上例给 5），必须逐段取。
- 做法：文本框任一 `paragraphs[j].list_type != 0` 即命中 GLB-28。输出已带该字段。
- 未覆盖：多层/复杂编号定义（语料文本框没有真正的编号内容，只用合成验了基础两态）。

### 7）VML 文本框 vs DrawingML 文本框

| OOXML 写法 | 落在 | `Shape.Type` |
|---|---|---|
| VML `w:pict/v:textbox`（浮动） | `Shapes` | 17（`msoTextBox`） |
| VML `w:pict/v:textbox`（`mso-position-…-relative:line`，合成） | `Shapes` | 17 |
| DrawingML `wps:txbx` + `wp:anchor`（校园便利店） | `Shapes` | **1**（矩形几何，不是 17） |
| DrawingML `wps:txbx` + `wp:inline`（合成） | `Shapes` | 17 |

即：**两者都在 `Shapes`**；`InlineShapes` 两者都取不到。不能靠 `Type` 认文本框（DrawingML 矩形报 1），
要用 `TextFrame.HasText`。

## 踩到的怪癖

- **`Shape.Type` 不是文本框判据**：VML 文本框报 17，DrawingML 矩形文本框报 1。判据用 `HasText`。
- **无文本框的图形取 `TextRange` 报 `0x80000008`**：`HasText=0` 时必须先挡掉。
- **组合自身 `TextRange` 也报 `0x80000008`**：必须下钻 `GroupItems`。
- **整段 `TextRange.Font` 混合格式时给 `Size=9999999`、`Name=None`**：字号/字体只能逐段/逐字符取。
- **空文本框 `HasText` 仍为真**、`TextRange.Text == "\r"`（据此可数到空框）。
- **`TextRange.Start/End` 与正文不同坐标系**，别拿它映射段落；`Anchor` 才行。
- `w:txbxContent` 全语料 17 个里有 1 个 `mc:Fallback` 重复（同一对象），去重后 16 个。
- 40 篇语料只有 2 篇有文本框，绝大多数篇是空跑。
