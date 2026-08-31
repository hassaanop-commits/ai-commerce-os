"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";

const NAV_ITEMS = [
  { label: "Overview", href: "/dashboard", enabled: true },
  { label: "Products", href: "/dashboard/products", enabled: true },
  { label: "AI Studio", href: "/dashboard/ai-studio", enabled: false },
  { label: "Listings", href: "/dashboard/listings", enabled: false },
  { label: "Marketplaces", href: "/dashboard/marketplaces", enabled: false },
  { label: "Analytics", href: "/dashboard/analytics", enabled: false },
  { label: "Team", href: "/dashboard/team", enabled: false },
  { label: "Settings", href: "/dashboard/settings", enabled: false },
  { label: "Billing", href: "/dashboard/billing", enabled: false },
];

export function Sidebar({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const pathname = usePathname();

  return (
    <>
      {isOpen ? <div className={styles.backdrop} onClick={onClose} aria-hidden="true" /> : null}
      <nav className={[styles.sidebar, isOpen ? styles.sidebarOpen : ""].join(" ")} aria-label="Primary">
        <div className={styles.brand}>AI Commerce OS</div>
        <ul className={styles.list}>
          {NAV_ITEMS.map((item) => {
            if (!item.enabled) {
              return (
                <li key={item.label} className={styles.itemDisabled} aria-disabled="true">
                  <span>{item.label}</span>
                  <span className={styles.badge}>Soon</span>
                </li>
              );
            }
            const isActive =
              item.href === "/dashboard" ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <li key={item.label}>
                <Link
                  href={item.href}
                  className={[styles.item, isActive ? styles.itemActive : ""].join(" ")}
                  onClick={onClose}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
