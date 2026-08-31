"use client";

import { useState, type ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";
import styles from "./DashboardShell.module.css";

export function DashboardShell({ children }: { children: ReactNode }) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <div className={styles.shell}>
      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
      <div className={styles.main}>
        <TopNav onMenuClick={() => setIsSidebarOpen((open) => !open)} />
        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
