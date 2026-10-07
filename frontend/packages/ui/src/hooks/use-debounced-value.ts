import { useEffect, useState } from "react";

/** 输入防抖：delay 毫秒内的连续变化只保留最后一个值（搜索框用）。 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
