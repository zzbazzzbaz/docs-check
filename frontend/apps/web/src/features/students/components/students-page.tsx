import { Card, CardContent } from "@repo/ui/components/card";
import { Input } from "@repo/ui/components/input";
import { Skeleton } from "@repo/ui/components/skeleton";
import { useDebouncedValue } from "@repo/ui/hooks/use-debounced-value";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PaginationFooter } from "@/components/pagination-footer";
import { toErrorMessage } from "@/lib/api";
import { studentsQueryOptions } from "../api";
import { StudentsTable } from "./students-table";

const PAGE_SIZE = 20;

export function StudentsPage() {
  const [keyword, setKeyword] = useState("");
  const [offset, setOffset] = useState(0);
  const q = useDebouncedValue(keyword.trim(), 300);

  const { data, isLoading, isError, error } = useQuery(studentsQueryOptions(q, offset, PAGE_SIZE));

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">我的学生</h1>
        <Input
          className="w-64"
          placeholder="搜索学号 / 姓名"
          value={keyword}
          onChange={(event) => {
            setKeyword(event.target.value);
            setOffset(0);
          }}
        />
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : isError ? (
        <p className="text-sm text-destructive">{toErrorMessage(error, "加载失败")}</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">
            {q ? "没有找到匹配的学生" : "名下暂无学生，请联系管理员分配"}
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <StudentsTable items={items} />
        </div>
      )}

      {items.length > 0 && (
        <PaginationFooter
          offset={offset}
          limit={PAGE_SIZE}
          total={total}
          onOffsetChange={setOffset}
        />
      )}
    </div>
  );
}
