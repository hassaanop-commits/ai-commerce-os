import type { ApprovalStatus } from "@/types/product";
import styles from "./ApprovalBadge.module.css";

const LABELS: Record<ApprovalStatus, string> = {
  not_required: "",
  pending_review: "Pending Review",
  approved: "Approved",
  rejected: "Rejected",
};

export function ApprovalBadge({ status }: { status: ApprovalStatus }) {
  if (status === "not_required") return null;
  return <span className={[styles.badge, styles[status]].join(" ")}>{LABELS[status]}</span>;
}
