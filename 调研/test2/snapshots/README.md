# 对账快照（进版本管理）

`test2/out/` 是**可重新生成**的对账产物，不进版本；这里放它的**压缩快照**，用途只有一个：
给正式项目的解析器重写提供**等价性验证的基线**（见 `docs/chat/9.26/技术设计.md` §7.2）。

## 内容

| 路径 | 内容 |
|---|---|
| `*.json.gz` | 490 个快照：自研侧（`own*`）+ WPS 侧（`wps*`）+ `foss`（已淘汰，仅留证据） |
| `reports/` | 子智能体的独立核验报告与逐表明细（`.md` / `verify_*.txt`） |
| `tools/` | 合成样张生成脚本与独立核验脚本（`synth_*.py` / `verify_*.py`） |

**没进版本**：`out/*.docx`（合成样张，可重新生成）、`probe_*.py`（现场探查的临时脚本）、
`paths_*.txt`、`*.log`、`*.pyc`。

## 用法

```bash
./snapshots.sh pack      # out/*.json → snapshots/*.json.gz（重新生成 out/ 后刷新快照）
./snapshots.sh unpack    # snapshots/*.json.gz → out/*.json
```

单看一个快照不用解压：

```bash
gunzip -c snapshots/某篇.own.json.gz | jq '.paragraphs[0]'
```

## 口径提醒

- 快照是 **2026-09-26** 那一轮对账的产物（八套 84 字段 / 421704 次比对 / 自研 99.999%），
  与 `README.md` 里记录的结论一一对应。
- **不要**手工编辑快照；要更新就重跑 `./run.sh` 再 `pack`。
- `foss` 那 40 个快照保留是为了留证据（"为什么不用 foss"用数据说话），**新代码不要依赖它**。
