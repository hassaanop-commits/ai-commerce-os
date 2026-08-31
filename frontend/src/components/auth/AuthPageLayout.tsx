import type { ReactNode } from "react";
import Link from "next/link";
import styles from "./AuthPageLayout.module.css";

export function AuthPageLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <Link href="/" className={styles.brand}>
          AI Commerce OS
        </Link>
        <h1 className={styles.title}>{title}</h1>
        {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
        {children}
      </div>
    </div>
  );
}
