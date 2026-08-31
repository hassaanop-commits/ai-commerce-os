"use client";

import { useState } from "react";
import Link from "next/link";
import { useOrganization } from "@/hooks/useOrganization";
import styles from "./OrgSwitcher.module.css";

export function OrgSwitcher() {
  const { organizations, selectedOrganization, selectOrganization } = useOrganization();
  const [isOpen, setIsOpen] = useState(false);

  if (!selectedOrganization) return null;

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setIsOpen((open) => !open)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className={styles.orgName}>{selectedOrganization.name}</span>
        <span className={styles.roleTag}>{selectedOrganization.role_name}</span>
      </button>
      {isOpen ? (
        <>
          <div className={styles.backdrop} onClick={() => setIsOpen(false)} aria-hidden="true" />
          <ul className={styles.menu} role="listbox">
            {organizations.map((org) => (
              <li key={org.organization_id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={org.organization_id === selectedOrganization.organization_id}
                  className={styles.menuItem}
                  onClick={() => {
                    selectOrganization(org.organization_id);
                    setIsOpen(false);
                  }}
                >
                  {org.name}
                </button>
              </li>
            ))}
            <li>
              <Link href="/organizations" className={styles.menuItem} onClick={() => setIsOpen(false)}>
                Create organization
              </Link>
            </li>
          </ul>
        </>
      ) : null}
    </div>
  );
}
