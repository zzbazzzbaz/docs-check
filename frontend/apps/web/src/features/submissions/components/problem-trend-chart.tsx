import { Card, CardContent, CardHeader, CardTitle } from "@repo/ui/components/card";
import { type ChartConfig, ChartContainer, ChartTooltip } from "@repo/ui/components/chart";
import { Skeleton } from "@repo/ui/components/skeleton";
import type { TooltipContentProps, TooltipValueType } from "recharts";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { toErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { TrendPoint } from "../lib/trend";

const CHART_HEIGHT_CLASS = "h-60";

const chartConfig = {
  total: { label: "总问题", color: "var(--chart-1)" },
} satisfies ChartConfig;

function TrendTooltip({ active, payload }: TooltipContentProps<TooltipValueType, string | number>) {
  const point = payload?.[0]?.payload as TrendPoint | undefined;
  if (!active || !point) {
    return null;
  }
  return (
    <div className="grid gap-1 rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">第 {point.sequence} 次提交</div>
      <div className="text-muted-foreground">{formatDateTime(point.createdAt)}</div>
      <div className="max-w-64 truncate text-muted-foreground" title={point.filename}>
        {point.filename}
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-6">
        <span className="text-muted-foreground">总问题</span>
        <span className="font-mono font-medium tabular-nums">{point.total}</span>
      </div>
    </div>
  );
}

/** 单线历史趋势（学生端 / 教师学生详情复用；x = 第 N 次提交，y = 总问题）。 */
export function ProblemTrendChart({
  points,
  title = "历史趋势（总问题）",
  emptyHint = "暂无成功审核结果",
  loading = false,
  error,
}: {
  points: TrendPoint[];
  title?: string;
  emptyHint?: string;
  loading?: boolean;
  error?: unknown;
}) {
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
        ) : points.length === 0 ? (
          <div
            className={`flex ${CHART_HEIGHT_CLASS} items-center justify-center text-sm text-muted-foreground`}
          >
            {emptyHint}
          </div>
        ) : (
          <ChartContainer config={chartConfig} className={`${CHART_HEIGHT_CLASS} w-full`}>
            <LineChart data={points} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="sequence"
                type="number"
                domain={["dataMin", "dataMax"]}
                allowDecimals={false}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
              <ChartTooltip content={(props) => <TrendTooltip {...props} />} />
              <Line
                dataKey="total"
                type="monotone"
                stroke="var(--color-total)"
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
