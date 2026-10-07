import { createFileRoute, redirect } from "@tanstack/react-router";

import { Forbidden } from "@/features/auth/components/forbidden";
import { SubmissionsPage } from "@/features/submissions/components/submissions-page";

export const Route = createFileRoute("/_auth/")({
  beforeLoad: ({ context }) => {
    if (context.me.role === "teacher") {
      throw redirect({ to: "/students" });
    }
  },
  component: HomePage,
});

function HomePage() {
  const { me } = Route.useRouteContext();

  if (me.role !== "student") {
    return <Forbidden />;
  }

  return <SubmissionsPage />;
}
