import styles from "./StatusBadge.module.css";

const LABELS: Record<string, string> = {
  draft: "Draft",
  active: "Active",
  archived: "Archived",
  pending: "Pending",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
  approved: "Approved",
  publishing: "Publishing",
  error: "Error",
  ended: "Ended",
  succeeded: "Succeeded",
  running: "Running",
};

export function StatusBadge({ status }: { status: string }) {
  const label = LABELS[status] ?? status;
  return <span className={[styles.badge, styles[status] ?? styles.default].join(" ")}>{label}</span>;
}
