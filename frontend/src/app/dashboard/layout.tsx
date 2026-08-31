import { redirect } from "next/navigation";
import { getCurrentUserServer, serverGet } from "@/lib/server-api";
import { AuthProvider } from "@/hooks/useAuth";
import { OrganizationProvider } from "@/hooks/useOrganization";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import type { OrganizationMembership } from "@/types/organization";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUserServer();
  if (!user) {
    redirect("/login");
  }

  const organizations = (await serverGet<OrganizationMembership[]>("/organizations")) ?? [];
  if (organizations.length === 0) {
    redirect("/organizations");
  }

  return (
    <AuthProvider user={user}>
      <OrganizationProvider organizations={organizations}>
        <DashboardShell>{children}</DashboardShell>
      </OrganizationProvider>
    </AuthProvider>
  );
}
