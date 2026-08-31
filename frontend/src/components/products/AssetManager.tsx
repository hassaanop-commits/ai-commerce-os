"use client";

import { useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import { aiApi } from "@/lib/ai-api";
import { productAssetsApi } from "@/lib/products-api";
import type { ProductAsset } from "@/types/product";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { AssetCard } from "./AssetCard";
import styles from "./AssetManager.module.css";

interface PendingUpload {
  id: string;
  previewUrl: string;
  progress: number;
  error: string | null;
}

export function AssetManager({
  organizationId,
  productId,
  assets,
  onAssetsChange,
}: {
  organizationId: string;
  productId: string;
  assets: ProductAsset[];
  onAssetsChange: (assets: ProductAsset[]) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [regeneratingAssetId, setRegeneratingAssetId] = useState<string | null>(null);

  const sortedAssets = [...assets].sort((a, b) => a.position - b.position);

  function handleFilesSelected(files: FileList | null) {
    if (!files || files.length === 0) return;
    Array.from(files).forEach(startUpload);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function startUpload(file: File) {
    const id = `${file.name}-${Date.now()}-${Math.random()}`;
    const previewUrl = URL.createObjectURL(file);
    setPendingUploads((prev) => [...prev, { id, previewUrl, progress: 0, error: null }]);

    productAssetsApi
      .upload(organizationId, productId, file, assets.length === 0, (percent) => {
        setPendingUploads((prev) => prev.map((p) => (p.id === id ? { ...p, progress: percent } : p)));
      })
      .then((asset) => {
        onAssetsChange([...assets, asset]);
        setPendingUploads((prev) => prev.filter((p) => p.id !== id));
        URL.revokeObjectURL(previewUrl);
      })
      .catch((error) => {
        const message = error instanceof ApiError ? error.detail : "Upload failed. Please try again.";
        setPendingUploads((prev) => prev.map((p) => (p.id === id ? { ...p, error: message } : p)));
      });
  }

  function dismissFailedUpload(id: string) {
    setPendingUploads((prev) => {
      const target = prev.find((p) => p.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }

  async function handleSetPrimary(assetId: string) {
    setListError(null);
    try {
      await productAssetsApi.update(organizationId, productId, assetId, { is_primary: true });
      onAssetsChange(assets.map((a) => ({ ...a, is_primary: a.id === assetId })));
    } catch (error) {
      setListError(error instanceof ApiError ? error.detail : "Something went wrong.");
    }
  }

  async function handleMove(assetId: string, direction: -1 | 1) {
    setListError(null);
    const index = sortedAssets.findIndex((a) => a.id === assetId);
    const targetIndex = index + direction;
    if (index === -1 || targetIndex < 0 || targetIndex >= sortedAssets.length) return;

    const current = sortedAssets[index];
    const target = sortedAssets[targetIndex];
    try {
      await Promise.all([
        productAssetsApi.update(organizationId, productId, current.id, { position: target.position }),
        productAssetsApi.update(organizationId, productId, target.id, { position: current.position }),
      ]);
      onAssetsChange(
        assets.map((a) => {
          if (a.id === current.id) return { ...a, position: target.position };
          if (a.id === target.id) return { ...a, position: current.position };
          return a;
        })
      );
    } catch (error) {
      setListError(error instanceof ApiError ? error.detail : "Something went wrong.");
    }
  }

  async function handleDelete(assetId: string) {
    setListError(null);
    try {
      await productAssetsApi.remove(organizationId, productId, assetId);
      onAssetsChange(assets.filter((a) => a.id !== assetId));
    } catch (error) {
      setListError(error instanceof ApiError ? error.detail : "Something went wrong.");
    }
  }

  async function handleApprove(assetId: string) {
    setListError(null);
    try {
      const updated = await productAssetsApi.approve(organizationId, productId, assetId);
      onAssetsChange(assets.map((a) => (a.id === assetId ? updated : a)));
    } catch (error) {
      setListError(error instanceof ApiError ? error.detail : "Something went wrong.");
    }
  }

  async function handleReject(assetId: string) {
    setListError(null);
    try {
      const updated = await productAssetsApi.reject(organizationId, productId, assetId);
      onAssetsChange(assets.map((a) => (a.id === assetId ? updated : a)));
    } catch (error) {
      setListError(error instanceof ApiError ? error.detail : "Something went wrong.");
    }
  }

  async function handleRegenerate(assetId: string) {
    setListError(null);
    setRegeneratingAssetId(assetId);
    try {
      const result = await aiApi.regenerateImage(organizationId, productId, assetId);
      // Regeneration always creates a brand-new asset (own AIRun, own
      // ProductAsset) rather than overwriting the source -- the old asset
      // stays exactly as it was, and the new one is appended pending review.
      if (result.status === "succeeded" && result.asset) {
        onAssetsChange([...assets, result.asset]);
      } else {
        setListError("Regeneration failed. Please try again.");
      }
    } catch (error) {
      setListError(error instanceof ApiError ? error.detail : "Something went wrong.");
    } finally {
      setRegeneratingAssetId(null);
    }
  }

  return (
    <div className={styles.manager}>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h2>Assets</h2>
          <p className={styles.lede}>Upload product photos. The first image becomes the primary image.</p>
        </div>
        <div className={styles.uploadButtonWrap}>
          <Button type="button" onClick={() => fileInputRef.current?.click()}>
            Upload image
          </Button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          multiple
          hidden
          onChange={(e) => handleFilesSelected(e.target.files)}
        />
      </div>

      {listError ? <Alert variant="error">{listError}</Alert> : null}

      {sortedAssets.length === 0 && pendingUploads.length === 0 ? (
        <div className={styles.emptyState}>
          <p>No assets yet. Upload your first product photo to get started.</p>
        </div>
      ) : (
        <div className={styles.grid}>
          {sortedAssets.map((asset, index) => (
            <AssetCard
              key={asset.id}
              organizationId={organizationId}
              productId={productId}
              asset={asset}
              canMoveUp={index > 0}
              canMoveDown={index < sortedAssets.length - 1}
              onSetPrimary={() => handleSetPrimary(asset.id)}
              onMoveUp={() => handleMove(asset.id, -1)}
              onMoveDown={() => handleMove(asset.id, 1)}
              onDelete={() => handleDelete(asset.id)}
              onApprove={() => handleApprove(asset.id)}
              onReject={() => handleReject(asset.id)}
              onRegenerate={() => handleRegenerate(asset.id)}
              isRegenerating={regeneratingAssetId === asset.id}
            />
          ))}
          {pendingUploads.map((upload) => (
            <div key={upload.id} className={styles.pendingCard}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={upload.previewUrl} alt="" className={styles.pendingImage} />
              {upload.error ? (
                <div className={styles.pendingError}>
                  <p>{upload.error}</p>
                  <button type="button" onClick={() => dismissFailedUpload(upload.id)}>
                    Dismiss
                  </button>
                </div>
              ) : (
                <div className={styles.progressOverlay}>
                  <div className={styles.progressTrack}>
                    <div className={styles.progressFill} style={{ width: `${upload.progress}%` }} />
                  </div>
                  <span>{upload.progress < 100 ? `Uploading ${upload.progress}%` : "Processing…"}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
