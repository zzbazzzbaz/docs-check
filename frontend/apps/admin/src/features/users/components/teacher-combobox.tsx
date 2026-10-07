import { Button } from "@repo/ui/components/button";
import { FormControl } from "@repo/ui/components/form";
import { Input } from "@repo/ui/components/input";
import { Popover, PopoverContent, PopoverTrigger } from "@repo/ui/components/popover";
import { useDebouncedValue } from "@repo/ui/hooks/use-debounced-value";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useState } from "react";

import { toErrorMessage } from "@/lib/api";
import { teacherOptionsQueryOptions } from "../api";

/** 「未分配」哨兵值（后端用 teacher_id: null 表示）。 */
export const NONE_TEACHER = "none";

interface TeacherComboboxProps {
  value: string;
  onChange: (value: string) => void;
  /** 当前值的兜底显示文案（编辑回显；打开列表后优先显示「姓名（工号）」）。 */
  selectedLabel?: string;
}

/** 指导教师选择：可搜索（姓名/工号，300ms 防抖，服务端模糊匹配）+ 下拉列表。 */
export function TeacherCombobox({ value, onChange, selectedLabel }: TeacherComboboxProps) {
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [labels, setLabels] = useState<Record<string, string>>({});
  const q = useDebouncedValue(keyword.trim(), 300);

  const { data, isLoading, isError, error } = useQuery({
    ...teacherOptionsQueryOptions(q),
    enabled: open,
  });

  // 缓存见过的「id → 姓名（工号）」，避免搜索后当前选中项失去显示名
  useEffect(() => {
    if (!data) {
      return;
    }
    setLabels((prev) => {
      const next = { ...prev };
      for (const teacher of data) {
        next[String(teacher.id)] = `${teacher.name}（${teacher.username}）`;
      }
      return next;
    });
  }, [data]);

  const options = data ?? [];
  const currentLabel =
    value === NONE_TEACHER ? "未分配" : (labels[value] ?? selectedLabel ?? "已选择教师");

  function select(next: string) {
    onChange(next);
    setOpen(false);
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setKeyword("");
        }
      }}
    >
      <PopoverTrigger asChild>
        <FormControl>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between font-normal"
          >
            <span className="truncate">{currentLabel}</span>
            <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
          </Button>
        </FormControl>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) p-0">
        <div className="border-b p-2">
          <Input
            autoFocus
            placeholder="搜索姓名 / 工号"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </div>
        <div className="max-h-60 overflow-y-auto p-1">
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
            onClick={() => select(NONE_TEACHER)}
          >
            未分配
            {value === NONE_TEACHER && <Check className="size-4" />}
          </button>
          {isLoading ? (
            <p className="px-2 py-1.5 text-sm text-muted-foreground">加载中…</p>
          ) : isError ? (
            <p className="px-2 py-1.5 text-sm text-destructive">
              {toErrorMessage(error, "加载失败")}
            </p>
          ) : options.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-muted-foreground">未找到教师</p>
          ) : (
            options.map((teacher) => (
              <button
                key={teacher.id}
                type="button"
                className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                onClick={() => select(String(teacher.id))}
              >
                <span className="truncate">
                  {teacher.name}（{teacher.username}）
                </span>
                {value === String(teacher.id) && <Check className="size-4 shrink-0" />}
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
