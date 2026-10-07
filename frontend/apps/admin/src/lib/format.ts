/** UTC ISO → 本地时间（zh-CN，24 小时制）；空值显示「—」。 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
