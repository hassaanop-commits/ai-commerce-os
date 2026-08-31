"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { OrganizationMembership } from "@/types/organization";

const STORAGE_KEY = "ai-commerce-os:selected-organization";

interface OrganizationContextValue {
  organizations: OrganizationMembership[];
  selectedOrganizationId: string | null;
  selectedOrganization: OrganizationMembership | null;
  selectOrganization: (organizationId: string) => void;
}

const OrganizationContext = createContext<OrganizationContextValue | null>(null);

export function OrganizationProvider({
  organizations,
  children,
}: {
  organizations: OrganizationMembership[];
  children: ReactNode;
}) {
  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string | null>(
    organizations[0]?.organization_id ?? null
  );

  useEffect(() => {
    // Purely a UX default for which workspace opens first -- never trusted
    // for authorization. The backend re-checks membership on every
    // organization-scoped request regardless of what's stored here.
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && organizations.some((org) => org.organization_id === stored)) {
      setSelectedOrganizationId(stored);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectOrganization = useCallback((organizationId: string) => {
    setSelectedOrganizationId(organizationId);
    window.localStorage.setItem(STORAGE_KEY, organizationId);
  }, []);

  const selectedOrganization =
    organizations.find((org) => org.organization_id === selectedOrganizationId) ?? null;

  return (
    <OrganizationContext.Provider
      value={{ organizations, selectedOrganizationId, selectedOrganization, selectOrganization }}
    >
      {children}
    </OrganizationContext.Provider>
  );
}

export function useOrganization(): OrganizationContextValue {
  const ctx = useContext(OrganizationContext);
  if (!ctx) {
    throw new Error("useOrganization must be used within an OrganizationProvider");
  }
  return ctx;
}
