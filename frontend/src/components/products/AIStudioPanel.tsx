"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api-client";
import { aiApi } from "@/lib/ai-api";
import { productAssetsApi } from "@/lib/products-api";
import type { AIRun, GenerateDescriptionResult, GenerateImageResult } from "@/types/ai";
import type { Product, ProductAsset } from "@/types/product";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "./StatusBadge";
import styles from "./AIStudioPanel.module.css";

type Phase = "idle" | "generating" | "draft" | "applying" | "applied" | "error";
type ImagePhase = "idle" | "generating" | "error";
type AssetDecisionState = "idle" | "deciding" | "approved" | "rejected" | "error";

type ApplyStatus = "idle" | "applying" | "applied" | "error";

const RUN_TYPE_LABELS: Record<string, string> = {
  "product_content.analyze": "Product analysis",
  "product_content.generate_description": "Description generation",
  "product_content.generate_title": "Title generation",
  "product_content.generate_tags": "Tags generation",
  "product_image.craft_prompt": "Image prompt",
  "product_image.generate": "Image generation",
};

function describeRunType(runType: string): string {
  return RUN_TYPE_LABELS[runType] ?? runType;
}

function describeFailure(category: string | null): string {
  switch (category) {
    case "provider_not_configured":
      return "AI generation isn't configured yet for this environment.";
    case "provider_timeout":
      return "The AI provider timed out. Please try again.";
    case "provider_rate_limited":
      return "The AI provider is busy right now. Please try again shortly.";
    case "invalid_response":
      return "The AI provider returned a response we couldn't use. Please try again.";
    case "capability_not_supported":
      return "This AI provider doesn't support image generation.";
    case "content_policy_violation":
      return "That request was rejected by content moderation. Try a different description.";
    default:
      return "AI generation failed. Please try again.";
  }
}

function formatCost(costUsd: string): string {
  const value = Number(costUsd);
  return `$${Number.isFinite(value) ? value.toFixed(6) : "0.000000"}`;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function retryCountOf(run: AIRun): number | null {
  const value = run.metadata?.retries;
  return typeof value === "number" && value > 0 ? value : null;
}

function currentTagsOf(product: Product): string[] {
  const tags = product.metadata?.tags;
  return Array.isArray(tags) ? tags.filter((tag): tag is string => typeof tag === "string") : [];
}

function ProviderModelCostLine({ run }: { run: AIRun }) {
  return (
    <p className={styles.meta}>
      Provider: <strong>{run.provider}</strong> · Model: <strong>{run.model}</strong> · Estimated cost:{" "}
      <strong>{formatCost(run.cost_usd)}</strong>
    </p>
  );
}

export function AIStudioPanel({
  organizationId,
  productId,
  product,
  onProductUpdated,
  onAssetChange,
}: {
  organizationId: string;
  productId: string;
  product: Product;
  onProductUpdated: (product: Product) => void;
  onAssetChange?: (asset: ProductAsset) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<GenerateDescriptionResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [titleApplyStatus, setTitleApplyStatus] = useState<ApplyStatus>("idle");
  const [titleApplyError, setTitleApplyError] = useState<string | null>(null);
  const [tagsApplyStatus, setTagsApplyStatus] = useState<ApplyStatus>("idle");
  const [tagsApplyError, setTagsApplyError] = useState<string | null>(null);

  const [imagePrompt, setImagePrompt] = useState("");
  const [imageVariations, setImageVariations] = useState(1);
  const [imagePhase, setImagePhase] = useState<ImagePhase>("idle");
  const [imageResult, setImageResult] = useState<GenerateImageResult | null>(null);
  const [imageErrorMessage, setImageErrorMessage] = useState<string | null>(null);
  const [assetDecisions, setAssetDecisions] = useState<Record<string, AssetDecisionState>>({});
  const [assetDecisionErrors, setAssetDecisionErrors] = useState<Record<string, string>>({});

  const [history, setHistory] = useState<AIRun[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  async function refreshHistory() {
    setHistoryLoading(true);
    try {
      const runs = await aiApi.listRuns(organizationId, productId);
      setHistory(runs);
      setHistoryError(null);
    } catch (error) {
      setHistoryError(error instanceof ApiError ? error.detail : "Something went wrong loading history.");
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    aiApi
      .listRuns(organizationId, productId)
      .then((runs) => {
        if (cancelled) return;
        setHistory(runs);
        setHistoryError(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setHistoryError(error instanceof ApiError ? error.detail : "Something went wrong loading history.");
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, productId]);

  async function handleGenerate() {
    setPhase("generating");
    setErrorMessage(null);
    setResult(null);
    // A fresh generation means any previous title/tags apply state no
    // longer describes the draft currently on screen.
    setTitleApplyStatus("idle");
    setTitleApplyError(null);
    setTagsApplyStatus("idle");
    setTagsApplyError(null);

    try {
      const generated = await aiApi.generateDescription(organizationId, productId);
      setResult(generated);
      if (generated.status === "succeeded" && generated.generated_description) {
        setPhase("draft");
      } else {
        setErrorMessage(describeFailure(generated.error_category));
        setPhase("error");
      }
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
      setPhase("error");
    } finally {
      refreshHistory();
    }
  }

  async function handleApply() {
    const successfulRun = result?.ai_runs.find(
      (run) => run.run_type === "product_content.generate_description" && run.status === "succeeded"
    );
    if (!successfulRun) return;

    setPhase("applying");
    setErrorMessage(null);
    try {
      const updatedProduct = await aiApi.applyDescription(organizationId, productId, successfulRun.id);
      onProductUpdated(updatedProduct);
      setPhase("applied");
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
      setPhase("error");
    }
  }

  async function handleApplyTitle() {
    const titleRun = result?.ai_runs.find(
      (run) => run.run_type === "product_content.generate_title" && run.status === "succeeded"
    );
    if (!titleRun) return;

    setTitleApplyStatus("applying");
    setTitleApplyError(null);
    try {
      const updatedProduct = await aiApi.applyTitle(organizationId, productId, titleRun.id);
      onProductUpdated(updatedProduct);
      setTitleApplyStatus("applied");
    } catch (error) {
      setTitleApplyError(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
      setTitleApplyStatus("error");
    }
  }

  async function handleApplyTags() {
    const tagsRun = result?.ai_runs.find(
      (run) => run.run_type === "product_content.generate_tags" && run.status === "succeeded"
    );
    if (!tagsRun) return;

    setTagsApplyStatus("applying");
    setTagsApplyError(null);
    try {
      const updatedProduct = await aiApi.applyTags(organizationId, productId, tagsRun.id);
      onProductUpdated(updatedProduct);
      setTagsApplyStatus("applied");
    } catch (error) {
      setTagsApplyError(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
      setTagsApplyStatus("error");
    }
  }

  const isBusy = phase === "generating" || phase === "applying";
  const hasDraft = result?.status === "succeeded" && !!result.generated_description;
  const descriptionRun = result?.ai_runs.find((run) => run.run_type === "product_content.generate_description");
  const titleRun = result?.ai_runs.find((run) => run.run_type === "product_content.generate_title");
  const tagsRun = result?.ai_runs.find((run) => run.run_type === "product_content.generate_tags");
  const generateButtonLabel = phase === "draft" || phase === "applied" || phase === "applying" ? "Regenerate" : "Generate description";

  async function handleGenerateImage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!imagePrompt.trim()) return;

    setImagePhase("generating");
    setImageErrorMessage(null);
    setImageResult(null);
    setAssetDecisions({});
    setAssetDecisionErrors({});

    try {
      const generated = await aiApi.generateImage(organizationId, productId, imagePrompt.trim(), imageVariations);
      setImageResult(generated);
      if (generated.status === "succeeded" && generated.assets.length > 0) {
        generated.assets.forEach((asset) => onAssetChange?.(asset));
        setAssetDecisions(Object.fromEntries(generated.assets.map((a) => [a.id, "idle" as const])));
        setImagePhase("idle");
      } else {
        setImageErrorMessage(describeFailure(generated.error_category));
        setImagePhase("error");
      }
    } catch (error) {
      setImageErrorMessage(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
      setImagePhase("error");
    } finally {
      refreshHistory();
    }
  }

  async function handleAssetDecision(assetId: string, decision: "approve" | "reject") {
    setAssetDecisions((prev) => ({ ...prev, [assetId]: "deciding" }));
    setAssetDecisionErrors((prev) => ({ ...prev, [assetId]: "" }));
    try {
      const updated =
        decision === "approve"
          ? await productAssetsApi.approve(organizationId, productId, assetId)
          : await productAssetsApi.reject(organizationId, productId, assetId);
      onAssetChange?.(updated);
      setImageResult((prev) =>
        prev
          ? {
              ...prev,
              asset: prev.asset?.id === assetId ? updated : prev.asset,
              assets: prev.assets.map((a) => (a.id === assetId ? updated : a)),
            }
          : prev
      );
      setAssetDecisions((prev) => ({ ...prev, [assetId]: decision === "approve" ? "approved" : "rejected" }));
    } catch (error) {
      setAssetDecisionErrors((prev) => ({
        ...prev,
        [assetId]: error instanceof ApiError ? error.detail : "Something went wrong. Please try again.",
      }));
      setAssetDecisions((prev) => ({ ...prev, [assetId]: "error" }));
    }
  }

  const isImageBusy = imagePhase === "generating";

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h2>AI Studio</h2>
        <p className={styles.lede}>
          Generate a product description with AI. Nothing is published until you review and apply it.
        </p>
      </div>

      <Card className={styles.card}>
        <div className={styles.section}>
          <h3>Current title</h3>
          <p>{product.title}</p>
        </div>

        <div className={styles.section}>
          <h3>Current description</h3>
          <p>{product.description || "No description yet."}</p>
        </div>

        <div className={styles.section}>
          <h3>Current tags</h3>
          <p>{currentTagsOf(product).length > 0 ? currentTagsOf(product).join(", ") : "No tags yet."}</p>
        </div>

        <Button type="button" onClick={handleGenerate} isLoading={phase === "generating"} disabled={isBusy}>
          {generateButtonLabel}
        </Button>

        {phase === "generating" ? (
          <p className={styles.status} role="status">
            Analyzing product and writing a draft…
          </p>
        ) : null}

        {errorMessage ? <Alert variant="error">{errorMessage}</Alert> : null}

        {hasDraft ? (
          <div className={styles.draft}>
            <span className={styles.draftBadge}>AI Draft — not yet applied</span>

            {result?.analysis ? (
              <div className={styles.section}>
                <h3>Analysis</h3>
                <p>{result.analysis}</p>
              </div>
            ) : null}

            <div className={styles.section}>
              <h3>AI draft description</h3>
              <p>{result?.generated_description}</p>
            </div>

            {descriptionRun ? <ProviderModelCostLine run={descriptionRun} /> : null}

            {phase === "applied" ? (
              <Alert variant="success">Applied to the product.</Alert>
            ) : (
              <Button type="button" onClick={handleApply} isLoading={phase === "applying"} disabled={isBusy}>
                Apply to product
              </Button>
            )}

            {result?.generated_title ? (
              <div className={styles.draft}>
                <div className={styles.section}>
                  <h3>AI draft title</h3>
                  <p>{result.generated_title}</p>
                </div>
                {titleRun ? <ProviderModelCostLine run={titleRun} /> : null}
                {titleApplyError ? <Alert variant="error">{titleApplyError}</Alert> : null}
                {titleApplyStatus === "applied" ? (
                  <Alert variant="success">Applied to the product.</Alert>
                ) : (
                  <Button
                    type="button"
                    onClick={handleApplyTitle}
                    isLoading={titleApplyStatus === "applying"}
                    disabled={titleApplyStatus === "applying"}
                  >
                    Apply title
                  </Button>
                )}
              </div>
            ) : null}

            {result?.generated_tags && result.generated_tags.length > 0 ? (
              <div className={styles.draft}>
                <div className={styles.section}>
                  <h3>AI draft tags</h3>
                  <p>{result.generated_tags.join(", ")}</p>
                </div>
                {tagsRun ? <ProviderModelCostLine run={tagsRun} /> : null}
                {tagsApplyError ? <Alert variant="error">{tagsApplyError}</Alert> : null}
                {tagsApplyStatus === "applied" ? (
                  <Alert variant="success">Applied to the product.</Alert>
                ) : (
                  <Button
                    type="button"
                    onClick={handleApplyTags}
                    isLoading={tagsApplyStatus === "applying"}
                    disabled={tagsApplyStatus === "applying"}
                  >
                    Apply tags
                  </Button>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
      </Card>

      <Card className={styles.card}>
        <form className={styles.imageForm} onSubmit={handleGenerateImage}>
          <TextField
            label="Describe the image"
            placeholder="e.g. clean studio product photo on a white background"
            value={imagePrompt}
            onChange={(e) => setImagePrompt(e.target.value)}
            disabled={isImageBusy}
          />
          <label className={styles.variationsLabel}>
            Variations
            <select
              value={imageVariations}
              onChange={(e) => setImageVariations(Number(e.target.value))}
              disabled={isImageBusy}
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
              <option value={4}>4</option>
            </select>
          </label>
          <Button type="submit" isLoading={imagePhase === "generating"} disabled={isImageBusy || !imagePrompt.trim()}>
            {imageVariations > 1 ? `Generate ${imageVariations} variations` : "Generate image"}
          </Button>
        </form>

        {imagePhase === "generating" ? (
          <p className={styles.status} role="status">
            Writing a prompt and generating the image…
          </p>
        ) : null}

        {imageErrorMessage ? <Alert variant="error">{imageErrorMessage}</Alert> : null}

        {imageResult && imageResult.variations.length > 0 ? (
          <div className={styles.draft}>
            {imageResult.image_prompt ? (
              <div className={styles.section}>
                <h3>Image prompt</h3>
                <p>{imageResult.image_prompt}</p>
              </div>
            ) : null}

            {imageResult.assets.length < imageResult.variations.length ? (
              <Alert variant="info">
                {imageResult.assets.length} of {imageResult.variations.length} variations generated successfully.
                See below for which one(s) failed and why.
              </Alert>
            ) : null}

            <div className={styles.variationsGrid}>
              {imageResult.variations.map((variation) => {
                if (variation.status === "failed") {
                  return (
                    <div key={`failed-${variation.index}`} className={styles.variationCard}>
                      <div className={styles.failedSlot}>
                        <span className={styles.failedBadge}>Variation {variation.index + 1} failed</span>
                        <p className={styles.failedMessage}>{variation.error_message}</p>
                      </div>
                    </div>
                  );
                }

                const asset = variation.asset;
                if (!asset) return null;
                const decision = assetDecisions[asset.id] ?? "idle";
                const decisionError = assetDecisionErrors[asset.id];
                const imageRun = imageResult.ai_runs.find((run) => run.id === asset.ai_run_id);
                return (
                  <div key={asset.id} className={styles.variationCard}>
                    <span className={styles.draftBadge}>
                      {asset.approval_status === "pending_review" ? "Pending review — not visible until approved" : null}
                      {asset.approval_status === "approved" ? "Approved" : null}
                      {asset.approval_status === "rejected" ? "Rejected" : null}
                    </span>

                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={productAssetsApi.fileUrl(organizationId, productId, asset.id)}
                      alt=""
                      className={styles.imagePreview}
                    />

                    {imageRun ? <ProviderModelCostLine run={imageRun} /> : null}

                    {decisionError ? <Alert variant="error">{decisionError}</Alert> : null}

                    {decision === "idle" || decision === "deciding" || decision === "error" ? (
                      <div className={styles.imageActions}>
                        <Button
                          type="button"
                          onClick={() => handleAssetDecision(asset.id, "approve")}
                          isLoading={decision === "deciding"}
                          disabled={decision === "deciding"}
                        >
                          Approve
                        </Button>
                        <Button
                          type="button"
                          variant="danger"
                          onClick={() => handleAssetDecision(asset.id, "reject")}
                          isLoading={decision === "deciding"}
                          disabled={decision === "deciding"}
                        >
                          Reject
                        </Button>
                      </div>
                    ) : null}

                    {decision === "approved" ? (
                      <Alert variant="success">Approved. It can now be set as the primary image from the Assets tab.</Alert>
                    ) : null}
                    {decision === "rejected" ? (
                      <Alert variant="info">Rejected. It stays visible in the Assets tab and can be deleted from there.</Alert>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </Card>

      <Card className={styles.card}>
        <div className={styles.section}>
          <h3>Generation history</h3>
        </div>

        {historyLoading && history === null ? <Spinner label="Loading history..." /> : null}

        {historyError ? <Alert variant="error">{historyError}</Alert> : null}

        {history && history.length === 0 ? (
          <p className={styles.status}>No AI generations yet for this product.</p>
        ) : null}

        {history && history.length > 0 ? (
          <ul className={styles.historyList}>
            {history.map((run) => {
              const retries = retryCountOf(run);
              return (
                <li key={run.id} className={styles.historyRow}>
                  <div className={styles.historyRowHeader}>
                    <StatusBadge status={run.status} />
                    <span className={styles.historyType}>{describeRunType(run.run_type)}</span>
                    <span className={styles.historyTime}>{formatTimestamp(run.created_at)}</span>
                  </div>
                  <p className={styles.meta}>
                    Provider: <strong>{run.provider}</strong> · Model: <strong>{run.model}</strong>
                  </p>
                  <p className={styles.meta}>
                    {run.input_tokens} in / {run.output_tokens} out tokens · Estimated cost:{" "}
                    <strong>{formatCost(run.cost_usd)}</strong>
                    {retries ? ` · Retried ${retries}×` : ""}
                  </p>
                  {run.status === "failed" && run.error_message ? (
                    <p className={styles.historyError}>{describeFailure(run.error_message)}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </Card>
    </div>
  );
}
