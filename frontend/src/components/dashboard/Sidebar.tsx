"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";

const NAV_ITEMS = [
  { label: "Overview", href: "/dashboard", enabled: true, highlightWhenActive: true },
  { label: "Products", href: "/dashboard/products", enabled: true, highlightWhenActive: true },
  // AI Studio and Listings are real, tested features -- they just don't have their own
  // top-level route yet, living instead as tabs on a product's detail page
  // (/dashboard/products/[id]). Rather than mark them "Soon" (they aren't) or link
  // somewhere that doesn't exist, these point at the product list -- where you'd land
  // to open one anyway -- with a label that says so upfront. highlightWhenActive is off
  // for both so they don't fight the real "Products" item for the active-state
  // highlight, since all three share the same href.
  { label: "AI Studio (open a product)", href: "/dashboard/products", enabled: true, highlightWhenActive: false },
  { label: "Listings (open a product)", href: "/dashboard/products", enabled: true, highlightWhenActive: false },
  { label: "Marketplaces", href: "/dashboard/marketplaces", enabled: false, highlightWhenActive: false },
  { label: "Analytics", href: "/dashboard/analytics", enabled: false, highlightWhenActive: false },
  { label: "Team", href: "/dashboard/team", enabled: false, highlightWhenActive: false },
  { label: "Settings", href: "/dashboard/settings", enabled: false, highlightWhenActive: false },
  { label: "Billing", href: "/dashboard/billing", enabled: false, highlightWhenActive: false },
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
              item.highlightWhenActive &&
              (item.href === "/dashboard" ? pathname === item.href : pathname.startsWith(item.href));
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
