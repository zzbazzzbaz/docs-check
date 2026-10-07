import { Button } from "@repo/ui/components/button";

interface PaginationFooterProps {
  offset: number;
  limit: number;
  total: number;
  onOffsetChange: (offset: number) => void;
}

/** 列表分页页脚：「第 x–y 条，共 n 条」+ 上一页/下一页。 */
export function PaginationFooter({ offset, limit, total, onOffsetChange }: PaginationFooterProps) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">
        第 {from}–{to} 条，共 {total} 条
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          上一页
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}
