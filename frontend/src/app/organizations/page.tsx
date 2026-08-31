import { redirect } from "next/navigation";
import { getCurrentUserServer, serverGet } from "@/lib/server-api";
import { CreateOrganizationForm } from "@/components/organizations/CreateOrganizationForm";
import { Card } from "@/components/ui/Card";
import type { OrganizationMembership } from "@/types/organization";
import styles from "./page.module.css";

export const metadata = { title: "Organizations · AI Commerce OS" };

export default async function OrganizationsPage() {
  const user = await getCurrentUserServer();
  if (!user) {
    redirect("/login");
  }

  const organizations = (await serverGet<OrganizationMembership[]>("/organizations")) ?? [];
  const hasOrganizations = organizations.length > 0;

  return (
    <div className={styles.page}>
      <Card className={styles.card}>
        <h1>{hasOrganizations ? "Create a new workspace" : "Create your workspace"}</h1>
        <p className={styles.lede}>
          {hasOrganizations
            ? "Spin up a separate workspace for another team or brand."
            : "You're not part of a workspace yet. Create one to get started."}
        </p>
        <CreateOrganizationForm />
      </Card>
      {hasOrganizations ? (
        <Card className={styles.card}>
          <h2>Your workspaces</h2>
          <ul className={styles.orgList}>
            {organizations.map((org) => (
              <li key={org.organization_id} className={styles.orgListItem}>
                <span>{org.name}</span>
                <span className={styles.roleTag}>{org.role_name}</span>
              </li>
            ))}
          </ul>
          <a href="/dashboard" className={styles.dashboardLink}>
            Go to dashboard →
          </a>
        </Card>
      ) : null}
    </div>
  );
}
