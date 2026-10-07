import type { components } from "@repo/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@repo/ui/components/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
} from "@repo/ui/components/chart";
import { Skeleton } from "@repo/ui/components/skeleton";
import type { TooltipContentProps, TooltipValueType } from "recharts";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { totalCount } from "@/features/submissions/lib/status";
import { toErrorMessage } from "@/lib/api";
import { formatMonthDay, formatTimestamp } from "@/lib/format";

type TeacherStatsSeries = components["schemas"]["TeacherStatsSeries"];

const LINE_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
] as const;

const CHART_HEIGHT_CLASS = "h-72";

const studentKey = (studentId: number) => `student-${studentId}` as const;

type StudentKey = ReturnType<typeof studentKey>;

/** 宽表行：按时间戳对齐所有学生；某生在该时间无成功提交则为 undefined（不画点）。 */
type MultiLineRow = { t: number } & Partial<Record<StudentKey, number | null>>;

function buildChartData(series: TeacherStatsSeries[]): {
  rows: MultiLineRow[];
  config: ChartConfig;
} {
  const valuesByStudent = series.map((item) => ({
    key: studentKey(item.student_id),
    points: item.points.map((point) => ({
      t: Date.parse(point.created_at),
      total: totalCount(point.counts),
    })),
  }));

  const timestamps = new Set<number>();
  for (const { points } of valuesByStudent) {
    for (const { t } of points) {
      timestamps.add(t);
    }
  }
  const sorted = [...timestamps].sort((a, b) => a - b);
  const indexByTimestamp = new Map(sorted.map((t, index) => [t, index]));
  const rows: MultiLineRow[] = sorted.map((t) => ({ t }));

  for (const { key, points } of valuesByStudent) {
    for (const { t, total } of points) {
      const index = indexByTimestamp.get(t);
      const row = index === undefined ? undefined : rows[index];
      if (row) {
        row[key] = total;
      }
    }
  }

  const config: ChartConfig = {};
  series.forEach((item, index) => {
    config[studentKey(item.student_id)] = {
      label: item.name || item.username,
      color: LINE_COLORS[index % LINE_COLORS.length],
    };
  });

  return { rows, config };
}

function MultiTrendTooltip({
  active,
  payload,
}: TooltipContentProps<TooltipValueType, string | number>) {
  if (!active || !payload?.length) {
    return null;
  }
  const entries = payload.filter((item) => item.value !== null && item.value !== undefined);
  const first = entries[0]?.payload as MultiLineRow | undefined;
  if (entries.length === 0 || first === undefined) {
    return null;
  }
  return (
    <div className="grid min-w-40 gap-1 rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">{formatTimestamp(first.t)}</div>
      <div className="grid gap-1">
        {entries.map((item) => (
          <div key={String(item.dataKey)} className="flex items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-[2px]"
              style={{ backgroundColor: item.color ?? item.stroke ?? "var(--chart-1)" }}
            />
            <span className="text-muted-foreground">{item.name}</span>
            <span className="ml-auto pl-4 font-mono font-medium tabular-nums">
              {Number(item.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 多线历史趋势（教师列表：每生一条线，x = 提交时间，y = 总问题）。 */
export function StudentTrendChart({
  series,
  title = "学生历史趋势（总问题）",
  emptyHint = "名下学生暂无成功审核记录",
  loading = false,
  error,
}: {
  series: TeacherStatsSeries[];
  title?: string;
  emptyHint?: string;
  loading?: boolean;
  error?: unknown;
}) {
  const { rows, config } = buildChartData(series);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className={`${CHART_HEIGHT_CLASS} w-full`} />
        ) : error !== undefined && error !== null ? (
          <div
            className={`flex ${CHART_HEIGHT_CLASS} items-center justify-center text-sm text-destructive`}
          >
            {toErrorMessage(error, "加载失败")}
          </div>
        ) : rows.length === 0 ? (
          <div
            className={`flex ${CHART_HEIGHT_CLASS} items-center justify-center text-sm text-muted-foreground`}
          >
            {emptyHint}
          </div>
        ) : (
          <ChartContainer config={config} className={`${CHART_HEIGHT_CLASS} w-full`}>
            <LineChart data={rows} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(value: number) => formatMonthDay(value)}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={32}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
              <ChartTooltip content={(props) => <MultiTrendTooltip {...props} />} />
              <ChartLegend content={<ChartLegendContent className="flex-wrap" />} />
              {series.map((item, index) => (
                <Line
                  key={item.student_id}
                  dataKey={studentKey(item.student_id)}
                  name={item.name || item.username}
                  type="monotone"
                  stroke={LINE_COLORS[index % LINE_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 4 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
