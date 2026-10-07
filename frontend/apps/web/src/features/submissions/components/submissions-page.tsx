import { Card, CardContent } from "@repo/ui/components/card";
import { Skeleton } from "@repo/ui/components/skeleton";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PaginationFooter } from "@/components/pagination-footer";
import { toErrorMessage } from "@/lib/api";
import { submissionsQueryOptions } from "../api";
import { SubmissionsTable } from "./submissions-table";
import { UploadButton } from "./upload-button";

const PAGE_SIZE = 20;

export function SubmissionsPage() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, isError, error } = useQuery(submissionsQueryOptions(offset, PAGE_SIZE));

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">我的提交</h1>
        <UploadButton />
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : isError ? (
        <p className="text-sm text-destructive">{toErrorMessage(error, "加载失败")}</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">
            还没有提交记录，点击「上传论文」开始自查
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <SubmissionsTable items={items} />
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
