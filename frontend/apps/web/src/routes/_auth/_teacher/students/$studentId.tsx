import { createFileRoute } from "@tanstack/react-router";

import { StudentDetailPage } from "@/features/students/components/student-detail-page";

export const Route = createFileRoute("/_auth/_teacher/students/$studentId")({
  component: StudentDetailRoute,
});

function StudentDetailRoute() {
  const { studentId } = Route.useParams();

  return <StudentDetailPage studentId={Number(studentId)} />;
}
