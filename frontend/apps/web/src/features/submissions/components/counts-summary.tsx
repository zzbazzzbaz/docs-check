import type { components } from "@repo/api-client";

import { countsSummary } from "../lib/status";

type Counts = components["schemas"]["Counts"];

/** 列表行内的四项计数紧凑展示：不符合 5 · 无法判定 1 · 未执行 0 · 未识别 0。 */
export function CountsSummary({ counts }: { counts: Counts }) {
  return <span className="text-sm text-muted-foreground">{countsSummary(counts)}</span>;
}
