import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";

import { UsersPage } from "@/features/users/components/users-page";

const searchSchema = z.object({
  role: z.enum(["student", "teacher"]).optional(),
});

export const Route = createFileRoute("/_auth/users")({
  validateSearch: searchSchema,
  component: UsersRoute,
});

function UsersRoute() {
  const { role } = Route.useSearch();

  return <UsersPage initialRole={role ?? "student"} />;
}
