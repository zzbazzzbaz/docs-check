import type { components } from "@repo/api-client";

type SubmissionListItem = components["schemas"]["SubmissionListItem"];
export type SubmissionStatus = SubmissionListItem["status"];
export type Counts = components["schemas"]["Counts"];

export const COUNT_FIELDS = ["fail", "undetermined", "not_run", "unrecognised"] as const;

export const COUNT_LABELS: Record<(typeof COUNT_FIELDS)[number], string> = {
  fail: "不符合",
  undetermined: "无法判定",
  not_run: "未执行",
  unrecognised: "未识别",
};

/** 详情页模块展示固定顺序（与引擎 `_SCOPE_ORDER` 一致）。 */
export const SCOPE_ORDER = [
  "封面",
  "中文摘要",
  "英文摘要",
  "目录",
  "正文",
  "参考文献",
  "致谢",
  "附录",
  "全文",
] as const;

export function isTerminal(status: SubmissionStatus): boolean {
  return status === "success" || status === "failed";
}

export function totalCount(counts: Counts): number {
  return COUNT_FIELDS.reduce((sum, field) => sum + counts[field], 0);
}

export function countsSummary(counts: Counts): string {
  return COUNT_FIELDS.map((field) => `${COUNT_LABELS[field]} ${counts[field]}`).join(" · ");
}

/** by_scope 按固定模块顺序排序，未知键追加在末尾。 */
export function orderedScopes(byScope: Record<string, Counts>): string[] {
  const known = SCOPE_ORDER.filter((scope) => byScope[scope] !== undefined);
  const extra = Object.keys(byScope).filter(
    (scope) => !(SCOPE_ORDER as readonly string[]).includes(scope),
  );
  return [...known, ...extra];
}
