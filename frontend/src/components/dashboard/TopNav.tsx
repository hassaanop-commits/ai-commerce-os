"use client";

import { OrgSwitcher } from "./OrgSwitcher";
import { UserMenu } from "./UserMenu";
import styles from "./TopNav.module.css";

export function TopNav({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className={styles.header}>
      <button
        type="button"
        className={styles.menuButton}
        onClick={onMenuClick}
        aria-label="Toggle navigation"
      >
        <span className={styles.menuIcon} aria-hidden="true" />
      </button>
      <div className={styles.spacer} />
      <OrgSwitcher />
      <UserMenu />
    </header>
  );
}
