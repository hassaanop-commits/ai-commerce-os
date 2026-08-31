import styles from "./SourceBadge.module.css";

const LABELS: Record<string, string> = {
  upload: "Uploaded",
  ai_generated: "AI Generated",
  processed: "Processed",
};

export function SourceBadge({ source }: { source: string }) {
  const label = LABELS[source] ?? source;
  return <span className={[styles.badge, styles[source] ?? styles.default].join(" ")}>{label}</span>;
}
