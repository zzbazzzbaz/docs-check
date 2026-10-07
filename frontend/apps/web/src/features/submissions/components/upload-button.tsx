import { Button } from "@repo/ui/components/button";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { type ChangeEvent, useRef } from "react";
import { toast } from "sonner";

import { uploadSubmission } from "@/features/submissions/api";

/** 与服务端 UPLOAD_MAX_BYTES 保持一致（50MB）。 */
const MAX_BYTES = 50 * 1024 * 1024;

export function UploadButton() {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: uploadSubmission,
    onSuccess: () => {
      toast.success("已提交，正在审核");
      void queryClient.invalidateQueries({ queryKey: ["submissions"] });
    },
  });

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // 允许再次选择同一个文件
    if (!file) {
      return;
    }
    if (!file.name.toLowerCase().endsWith(".docx")) {
      toast.error("仅支持 .docx 文件");
      return;
    }
    if (file.size === 0) {
      toast.error("请选择文件");
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error("文件超过 50MB 限制");
      return;
    }
    mutation.mutate(file);
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={onFileChange}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={mutation.isPending}>
        <Upload />
        {mutation.isPending ? "上传中…" : "上传论文"}
      </Button>
    </>
  );
}
