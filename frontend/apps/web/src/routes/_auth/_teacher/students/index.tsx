import { createFileRoute } from "@tanstack/react-router";

/** M1 占位：M3 替换为真实的「我的学生」列表。 */
export const Route = createFileRoute("/_auth/_teacher/students/")({
  component: StudentsPage,
});

function StudentsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">我的学生</h1>
      <p className="text-sm text-muted-foreground">页面开发中。</p>
    </div>
  );
}
