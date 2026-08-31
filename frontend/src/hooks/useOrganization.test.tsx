import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrganizationProvider, useOrganization } from "./useOrganization";
import type { OrganizationMembership } from "@/types/organization";

const orgs: OrganizationMembership[] = [
  { organization_id: "org-1", name: "Acme", slug: "acme", role_key: "owner", role_name: "Owner", joined_at: null },
  {
    organization_id: "org-2",
    name: "Widgets Inc",
    slug: "widgets-inc",
    role_key: "member",
    role_name: "Member",
    joined_at: null,
  },
];

function Probe() {
  const { selectedOrganization, selectOrganization } = useOrganization();
  return (
    <div>
      <p>{selectedOrganization?.name}</p>
      <button onClick={() => selectOrganization("org-2")}>Switch to Widgets Inc</button>
    </div>
  );
}

describe("useOrganization", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("defaults the selected organization to the first one provided", () => {
    render(
      <OrganizationProvider organizations={orgs}>
        <Probe />
      </OrganizationProvider>
    );

    expect(screen.getByText("Acme")).toBeInTheDocument();
  });

  it("updates the selected organization and persists the choice", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationProvider organizations={orgs}>
        <Probe />
      </OrganizationProvider>
    );

    await user.click(screen.getByRole("button", { name: /switch to widgets inc/i }));

    expect(await screen.findByText("Widgets Inc")).toBeInTheDocument();
    expect(window.localStorage.getItem("ai-commerce-os:selected-organization")).toBe("org-2");
  });

  it("restores a previously selected organization from localStorage", () => {
    window.localStorage.setItem("ai-commerce-os:selected-organization", "org-2");

    render(
      <OrganizationProvider organizations={orgs}>
        <Probe />
      </OrganizationProvider>
    );

    expect(screen.getByText("Widgets Inc")).toBeInTheDocument();
  });
});
