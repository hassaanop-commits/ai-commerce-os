"use client";

import { useState } from "react";
import { productAssetsApi } from "@/lib/products-api";
import type { ProductAsset } from "@/types/product";
import { ApprovalBadge } from "./ApprovalBadge";
import { SourceBadge } from "./SourceBadge";
import { StatusBadge } from "./StatusBadge";
import styles from "./AssetCard.module.css";

export function AssetCard({
  organizationId,
  productId,
  asset,
  canMoveUp,
  canMoveDown,
  onSetPrimary,
  onMoveUp,
  onMoveDown,
  onDelete,
  onApprove,
  onReject,
  onRegenerate,
  isRegenerating = false,
}: {
  organizationId: string;
  productId: string;
  asset: ProductAsset;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onSetPrimary: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  onApprove?: () => void;
  onReject?: () => void;
  onRegenerate?: () => void;
  isRegenerating?: boolean;
}) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isPromptOpen, setIsPromptOpen] = useState(false);
  // Uploads (approval_status 'not_required') behave exactly as before this
  // phase; only AI-generated/processed assets can ever be primary-ineligible.
  const canBecomePrimary = asset.approval_status === "approved" || asset.approval_status === "not_required";
  const isPendingReview = asset.approval_status === "pending_review";

  return (
    <div className={styles.card}>
      <div className={styles.imageWrap}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={productAssetsApi.fileUrl(organizationId, productId, asset.id)}
          alt=""
          className={styles.image}
        />
        {asset.is_primary ? <span className={styles.primaryBadge}>Primary</span> : null}
        <span className={styles.statusWrap}>
          <StatusBadge status={asset.status} />
        </span>
        <span className={styles.approvalWrap}>
          <ApprovalBadge status={asset.approval_status} />
        </span>
        <span className={styles.sourceWrap}>
          <SourceBadge source={asset.source} />
        </span>
      </div>

      {asset.image_prompt ? (
        <div className={styles.promptWrap}>
          <button type="button" className={styles.promptToggle} onClick={() => setIsPromptOpen((v) => !v)}>
            {isPromptOpen ? "Hide AI prompt" : "View AI prompt"}
          </button>
          {isPromptOpen ? <p className={styles.promptText}>{asset.image_prompt}</p> : null}
        </div>
      ) : null}

      <div className={styles.actions}>
        <button type="button" onClick={onMoveUp} disabled={!canMoveUp} aria-label="Move earlier">
          ←
        </button>
        <button type="button" onClick={onMoveDown} disabled={!canMoveDown} aria-label="Move later">
          →
        </button>
        {!asset.is_primary && canBecomePrimary ? (
          <button type="button" onClick={onSetPrimary}>
            Set primary
          </button>
        ) : null}
        {isPendingReview && onApprove ? (
          <button type="button" onClick={onApprove}>
            Approve
          </button>
        ) : null}
        {isPendingReview && onReject ? (
          <button type="button" className={styles.danger} onClick={onReject}>
            Reject
          </button>
        ) : null}
        {asset.source === "ai_generated" && onRegenerate ? (
          <button type="button" onClick={onRegenerate} disabled={isRegenerating}>
            {isRegenerating ? "Regenerating…" : "Regenerate"}
          </button>
        ) : null}
        {isConfirmingDelete ? (
          <>
            <button type="button" className={styles.danger} onClick={onDelete}>
              Confirm delete
            </button>
            <button type="button" onClick={() => setIsConfirmingDelete(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className={styles.danger} onClick={() => setIsConfirmingDelete(true)}>
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
