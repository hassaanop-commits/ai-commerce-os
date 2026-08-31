import type { ReactNode } from "react";
import styles from "./Alert.module.css";

type AlertVariant = "error" | "success" | "info";

export function Alert({ variant, children }: { variant: AlertVariant; children: ReactNode }) {
  return (
    <div className={[styles.alert, styles[variant]].join(" ")} role={variant === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}
