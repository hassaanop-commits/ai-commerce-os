"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import styles from "./UserMenu.module.css";

export function UserMenu() {
  const { user, logout, isLoggingOut } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const initial = (user.full_name.trim().charAt(0) || user.email.charAt(0)).toUpperCase();

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setIsOpen((open) => !open)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Account menu"
      >
        <span className={styles.avatar} aria-hidden="true">
          {initial}
        </span>
      </button>
      {isOpen ? (
        <>
          <div className={styles.backdrop} onClick={() => setIsOpen(false)} aria-hidden="true" />
          <div className={styles.menu} role="menu">
            <div className={styles.menuHeader}>
              <p className={styles.menuName}>{user.full_name}</p>
              <p className={styles.menuEmail}>{user.email}</p>
            </div>
            <button
              type="button"
              role="menuitem"
              className={styles.menuItem}
              onClick={() => logout()}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? "Signing out..." : "Sign out"}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
