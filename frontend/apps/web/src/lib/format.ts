/** UTC ISO → 本地时间（zh-CN，24 小时制）；空值显示「—」。 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  return formatTimestamp(new Date(value).getTime());
}

/** 时间戳 → 本地时间（zh-CN，24 小时制）。 */
export function formatTimestamp(value: number): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

/** 时间戳 → 本地「MM-DD」（图表刻度用）。 */
export function formatMonthDay(value: number): string {
  const date = new Date(value);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${month}-${day}`;
}
