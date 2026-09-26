# WPS 表格边框取值（`wps_borders.py`）

## 脚本与运行

- 取值脚本：`test2/docxfmt/wps_borders.py`（容器内跑，pywpsrpc + 标准库）
- 产出：`<outdir>/<stem>.wpsborders.json`
- 校验脚本（本地）：`test2/out/verify_borders.py`，把 WPS 边框与 OOXML 逐表对账，结果见
  `test2/out/verify_borders.txt`
- 合成/探测脚本（都在 `out/`，不污染 corpus）：
  `gen_border_synth.py`（造 6 个受控边框场景 → `synth-borders.docx`）、
  `synth_three_real.py`（把 `论文初稿` 表1 的直接边框删掉、只留样式 21 三线表）、
  `probe_borders.py` / `probe_borders2.py`（打印 WPS 边框 API 细节）、
  `probe_rows.py`（Rows.Item 探测）、`analyze_corpus_tables.py` / `dump_tbl_xml.py` /
  `dump_tbl_styles.py`（OOXML 侧）

```bash
cd test2
(cd corpus && ls -1 *.docx | sed 's|^|/in/|') > out/paths_bd.txt
docker run --rm --platform linux/amd64 \
  -v "$PWD/corpus:/in:ro" -v "$PWD/out:/out" \
  -v "$PWD/docxfmt/wps_borders.py:/opt/wps_borders.py:ro" \
  thesis-format-review/wps:dev \
  bash -lc "python3 /opt/wps_borders.py --outdir /out --list /out/paths_bd.txt"

# 对账
uv run python out/verify_borders.py
```

先跑的 3 篇：`2206181072_李煜…`（42 表）、`main-text-figure-table-caption-format`（5 表）、
`论文初稿`（2 表）；再全跑 40 篇 + 3 个合成文档。

## 输出

`counts.tables` 与 `doc.Tables.Count` 一致（只数顶层表）。每个表除了规格里的
`i/rows/cols/edges/cells`，另加了几个诊断字段：`enable`（`Table.Borders.Enable`）、
`style`（`Table.Style`，见怪癖 4，别用）、`row1_edges`/`col1_edges`
（`Rows.Item(1).Borders` / `Columns.Item(1).Borders`，见怪癖 1）、`sample_rows`/`sample_cols`。
`cells` 只采前 2 行 × 前 3 列；`Cell.Borders` 只有 4 条边，`inside_h`/`inside_v` 给 `null`。
取不到一律 `null`，不抛。

## 实测结果摘要

| 项 | 结果 |
|---|---|
| 语料 | 40 篇 / **228** 个顶层表格（WPS 与 OOXML 表数逐篇相等）|
| 单元格对账（4 边） | 4644/4768 = 97.40% 精确；**存在性一致率 100%**；**194/228 表 100%** |
| 表级对账（6 边） | 1337/1368 = 97.73%；**205/228 表 100%** |
| `Row1.Borders` 可用 | 211/228（含 `vMerge` 的 17 张表拿不到，见怪癖 1）|
| `LineStyle` 取值 | 只出现 **0 / 1 / 9999999**，没出现点线/双线等其它值 |
| 真三线表 | **210/228 = 92.1%**（用 WPS 信息判：正判 210，误判 1）|

## 六点结论

### 1. 可用性（逐个试过）

| 对象 | 结论 |
|---|---|
| `Table.Borders.Item(k)` k=1..6 | ✅ `LineStyle` / `LineWidth` / `Color` / `Visible` 都能取 |
| `Table.Borders.Enable` | ✅ 返回 `-1`（True）/ `0` |
| `Cell.Borders.Item(k)` | ⚠️ 只有 **k=1..4**（top/left/bottom/right）能取；`Item(5)/(6)` 抛异常（`Count` 报 6 是假的）|
| `Row.Borders` / `Column.Borders` | ⚠️ 存在，但语义不稳：列级 `insideH/insideV` 经常给 `9999999`；行级底边和 `Table.Borders` 对不上。**别单独用** |
| `Table.Style` | ❌ 返回的是**文档默认表样式名**（本语料恒为“网格型”），不是本表实际引用，弃用 |
| `Borders.Item("Top")` 字符串索引 | ❌ 只吃整数枚举 |

`Borders.Count`：Table=8、Cell=6（但有效可取的只有 4）。

### 2. `LineStyle` / `LineWidth`

- **`LineStyle` 取值分布**：全语料只出现 `0`（无线）、`1`（single）、`9999999`（`wdUndefined`，
  即“该边在单元格之间不一致”）。没有出现 2~23 的其它线型。
- **`LineStyle=0` 时 `LineWidth` 有 0 和 2 两种**（全语料单元格样本：0 出现 2935 次、2 出现 88 次）：
  - `0` = 显式写死“无框线”（`w:val="nil"`，或表级边界边的 `w:val="none"`）；
  - `2`（=0.25pt 极细线）= **该边从未设过**（含内部边的 `none`/缺省）。
  - 两者 `Visible` 都是 `False`，渲染上都不可见。
- `LineStyle=9999999` 时 `LineWidth` 也是 `9999999`。
- **宽度单位确认**：`OOXML w:sz="4"` ↔ `LineWidth=4`、`sz="8"` ↔ `8`、`sz="12"` ↔ `12`，
  即 1/8 pt，直接一一对应，无需换算。

### 3. 优先级：`Table.Borders` 报的是**有效值**，不是直接值

三条证据：

1. **纯样式表**（`synth-borders` T1：只有表样式 `Table Grid`、没有任何直接边框）→
   `Table.Borders` 六条边全报 `1/4`。→ 表样式的 `tblPr/tblBorders` 被算进来了。
2. **单元格顶掉表级**（李煜表2：`tblBorders.top=sz8`，首行 `tcBorders.top=sz4`）→
   `Table.Borders.top` 报 `1/4`（跟单元格），不是 `1/8`。
3. **单元格之间不一致 → 9999999**（`synth-borders` T4：只给 cell(1,1) 设了顶边）→
   `Table.Borders.top = 9999999/9999999`，而 `Cell(1,1).Borders.top = 1/8`、`Cell(1,2).top = 0`。

所以 **`Table.Borders` 是“把所有单元格的有效边框合并起来”的视图**，
`Cell.Borders` 是**单个单元格**的有效边框；两者都在“有效值”这一层。

至于“行 `trPr`”那一级：**OOXML 的 `w:trPr` 根本没有边框子元素**
（全语料 228 个表、0 处 `trPr/tblBorders`；语料里的行边框都落到每个 `tcPr/tcBorders`）。
WPS 的 `Row.Borders` 是派生视图，不构成独立一级。

### 4. 表格样式：`tblBorders` 认，`tblStylePr` 条件格式**不认**

- 表样式的 `tblPr/tblBorders`：**认**（见上 T1；`论文初稿` 样式21 的 top/bottom=12 也能报出来）。
- 表样式的 `tblStylePr` 条件格式：**不认**。三线表常把“表头下框线”放在
  `tblStylePr type="firstRow"` 里，WPS 会丢这条线。实测（`out/synth-borders.docx`）：

  | 表 | 构造 | WPS `Cell(1,1).Borders.bottom` |
  |---|---|---|
  | T5 | 纯样式三线表（firstRow 条件里 bottom=sz6，无直接边框）| `0/0` ❌ 丢了 |
  | T6 | 同样的线但写成**直接** `tcBorders` | `1/6` ✅ |

  用**真实**的 `论文初稿` 样式21（把表1的直接边框删掉，`synth_three_real.py`）复现同样结果：
  表级 top/bottom 报 `1/12`（样式 base 认），但表头那条 `firstRow` 线报 `0/0`。
  补上 `w:tblLook firstRow="1"` 也一样（`synth-three-style-only-look.docx`）。

**对 TXT-49 的影响**：若某篇的三线表**只靠 `tblStylePr`** 实现，WPS 会漏掉表头下框线，
判成“两线表”。本语料没踩到——`论文初稿`/`数学论文初稿` 虽用样式21，但每个表都把三条线
**同时写成了直接 `tcBorders`**（Word 应用样式时会 flatten），所以 WPS 仍看得到。

### 5. 与 OOXML 逐表对账

- **单元格**（WPS `Cell.Borders` 4 边 vs OOXML 有效单元格 = 样式base⊕直接`tblBorders`⊕`tcBorders`
  ⊕边界映射）：4768 处里
  - 精确一致 4644（97.40%）；
  - “均无、但宽度表示不同” 72（OOXML `none` 记 0、WPS 记 2，**存在性一致**）；
  - WPS 拿不到单元格 52（`vMerge` 合并位，`Cell(r,c)` 返回 `None`）；
  - **真正的“有线/无线”冲突 0 处** → 存在性 100% 一致；**194/228 表逐表 100%**。
- **表级**（WPS `Table.Borders` 6 边 vs 我用单元格合并出的模型）：1337/1368 = 97.73%。
  **205/228 表逐表 100%**，23 张有差异；31 处不一致全是**“表级合并视图”的建模差异**，分两类，
  都不是边框语义冲突（同一批表的单元格级是一致的）：
  - 单行 / 单列表没有内部边界：我的模型对空集判 `9999999`，WPS 直接给具体的 `off`
    （如李煜表33/34 两个 1×1 表）；
  - 含 `gridSpan`/`vMerge` 的表，边界单元格取值不同 → 一方 `9999999`、另一方具体值
    （如李煜表11/13 的 `bottom`：WPS=1/4，模型=1/8）。
- 所以“WPS 报有效值、OOXML 只有直接值”导致的差异**是预期**：拿 `Table.Borders` 去对
  OOXML 的 `tblPr/tblBorders` 直接值会大量对不上，必须先把 OOXML 侧按同样的级联合成到
  “有效值”再比（`verify_borders.py` 就是这么比的）。

### 6. 三线表的可判性

- **OOXML 真值：228 个表里 210 个是真三线表（92.1%）**——顶线 + 表头下线 + 底线，
  无左右线、无内部竖线、无其它横线。
- **拿 WPS 信息判**（`Table.Borders` 六边 + 前 2 行的 `Cell.Borders.bottom`）：
  正判 210 / 210，误判 1 —— `雷家琪` 表11 的**表级底线** WPS 报 `1/4`，而该表在 OOXML 里
  没有底线（`Normal Table` 无边框、末行也没写底边）；这是 WPS 表级视图的偏差，单元格级查不出。
- **够不够判 TXT-49**：**够，但必须逐单元格读 `Bottom`**，不能只看 `Table.Borders`：
  - 三线表的 `Table.Borders.insideH` 因为“表头行与正文行不同”而报 **`9999999`**，
    本身不能当作“无线”；
  - 只有把每个单元格的 `Borders.Bottom`（以及 `Left/Right`）读出来，
    才能确认“横线只出现在表头行下、其它行没有”。
  - **2 行 × 3 列的样本在本语料上刚好够**（正判 210/210），因为语料里的三线表形态很单一
    （都是“第 1 行上下线 + 第 2 行顶线，其余行无”）。要稳妥应读全部行：
    例如 `李煜` 表2 有 15 行，只有读全行才能确认第 3 行以后确实没有横线；
    若某表从第 3 行起才出现横线且各行不一致（`insideH` 会报 `9999999`），只看前 2 行会误判。
  - `vMerge` 合并位的单元格 WPS 给 `None`，需要用合并区左上角那个单元格的值代替。

**真三线表清单**（完整逐表在 `out/verify_borders.txt`；下面是按篇汇总）：

- 11 篇真实论文（149 个）：`李煜` 35、`王雨诺` 27、`电影推荐` 23、`雷家琪` 21、`肖瑶` 13、
  `王姝涵` 9、`季超` 7、`校园便利店` 5、`谢才智` 5、`论文初稿` 2、`数学论文初稿` 2
- 29 篇规则样张 / 合成基线（61 个）：`main-text-figure-table-caption-format` 5（表1~5）；
  其余 28 篇各 2 个（都是 表1(6×5) + 表2(3×5) 的样例表，含 `synth-page-setup-variants`）

明细（真实论文）：雷家琪 表1~10,12~18,27~30；王姝涵 表2~10；季超 表1~7；
李煜 表2~19,21,22,24,26~32,35~42；肖瑶 表1~13；电影推荐 表1~23；
校园便利店 表1~5；谢才智 表1~5；王雨诺 表1~27；论文初稿/数学论文初稿 表1~2。

## 踩到的怪癖

1. **含 `vMerge` 的表，`Rows.Item(k)` 全部返回 `None`**（不是抛异常）。
   全语料 228 个表：211 个无 `vMerge` → `Rows.Item(1)` 正常；17 个有 `vMerge` → 全 `None`，
   一一对应，无例外。所以 `Row.Borders` 在这 17 张表上取不到（`Rows.Count` 却是对的）。
2. **`Cell.Borders` 的 `Count=6` 是假的**，`Item(5)/(6)`（insideH/insideV）必抛；单元格没有内部线。
3. **`Column.Borders` 的 `insideH/insideV` 经常是 `9999999`**，即使该列竖线明明一致。
4. **`Table.Style` 不可信**：给的是文档默认表样式名（本语料全报“网格型”），
   与本表 `w:tblStyle` 无关。要拿样式名只能从 OOXML 读。
5. **`LineStyle=0` 时 `LineWidth` 有 0/2 两义**：0=显式无、2=从未设过。
6. **表样式 `tblStylePr` 条件格式不生效**（见结论 4）。
7. **`Table.Borders` 对三线表报 `insideH=9999999`**：这是“单元格间不一致”的正常表达，
   不是取不到。
8. **`gridAfter` 幻影列**：行里 `w:trPr/w:gridAfter` 会让表格的逻辑列数比实际 `tc` 多，
   对账时必须按实际存在的单元格位置算，否则会把空列当成“无线”而误判（三线表判定曾因此出错）。
9. `Table.Borders.Enable` 为 `-1`（True）时表示这张表启用了边框视图，`0` 表示单元格都没边。

## 未改动 `test2/docxfmt/` 下已有文件

只新增了 `test2/docxfmt/wps_borders.py`；临时脚本与合成文档都在 `test2/out/`。
