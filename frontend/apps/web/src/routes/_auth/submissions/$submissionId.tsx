import { createFileRoute } from "@tanstack/react-router";

import { SubmissionDetailPage } from "@/features/submissions/components/submission-detail-page";

export const Route = createFileRoute("/_auth/submissions/$submissionId")({
  component: SubmissionDetailRoute,
});

function SubmissionDetailRoute() {
  const { submissionId } = Route.useParams();

  return <SubmissionDetailPage submissionId={Number(submissionId)} />;
}
