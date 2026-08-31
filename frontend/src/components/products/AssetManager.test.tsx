import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetManager } from "./AssetManager";
import { aiApi } from "@/lib/ai-api";
import { productAssetsApi } from "@/lib/products-api";
import { ApiError } from "@/lib/api-client";
import type { GenerateImageResult } from "@/types/ai";
import type { ProductAsset } from "@/types/product";

vi.mock("@/lib/products-api", () => ({
  productAssetsApi: {
    upload: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    fileUrl: vi.fn((_orgId: string, _productId: string, assetId: string) => `/file/${assetId}`),
  },
}));

vi.mock("@/lib/ai-api", () => ({
  aiApi: {
    regenerateImage: vi.fn(),
  },
}));

const readyAsset: ProductAsset = {
  id: "a1",
  product_id: "p1",
  source: "upload",
  status: "ready",
  approval_status: "not_required",
  url: "/file/a1",
  is_primary: true,
  position: 1,
  asset_type: "image",
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
};

const pendingReviewAsset: ProductAsset = {
  id: "a2",
  product_id: "p1",
  source: "ai_generated",
  status: "ready",
  approval_status: "pending_review",
  url: "/file/a2",
  is_primary: false,
  position: 2,
  asset_type: "image",
  error_message: null,
  ai_run_id: "run-1",
  derived_from_asset_id: null,
  image_prompt: "A red ceramic mug on a white studio background.",
  created_at: "2026-01-01T00:00:00Z",
};

describe("AssetManager", () => {
  beforeEach(() => {
    vi.mocked(productAssetsApi.upload).mockReset();
    vi.mocked(productAssetsApi.update).mockReset();
    vi.mocked(productAssetsApi.remove).mockReset();
    vi.mocked(productAssetsApi.approve).mockReset();
    vi.mocked(productAssetsApi.reject).mockReset();
    vi.mocked(aiApi.regenerateImage).mockReset();
  });

  it("shows an empty state when there are no assets", () => {
    render(<AssetManager organizationId="org-1" productId="p1" assets={[]} onAssetsChange={vi.fn()} />);

    expect(screen.getByText(/no assets yet/i)).toBeInTheDocument();
  });

  it("renders an existing primary asset with a primary badge", () => {
    render(
      <AssetManager organizationId="org-1" productId="p1" assets={[readyAsset]} onAssetsChange={vi.fn()} />
    );

    expect(screen.getByText("Primary")).toBeInTheDocument();
  });

  it("uploads a selected file and reports it through onAssetsChange", async () => {
    vi.mocked(productAssetsApi.upload).mockResolvedValue(readyAsset);
    const onAssetsChange = vi.fn();

    const { container } = render(
      <AssetManager organizationId="org-1" productId="p1" assets={[]} onAssetsChange={onAssetsChange} />
    );

    const file = new File(["fake-image-bytes"], "photo.jpg", { type: "image/jpeg" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const user = userEvent.setup();
    await user.upload(input, file);

    await waitFor(() => expect(onAssetsChange).toHaveBeenCalledWith([readyAsset]));
    // First asset uploaded to an empty product automatically becomes primary.
    expect(productAssetsApi.upload).toHaveBeenCalledWith("org-1", "p1", file, true, expect.any(Function));
  });

  it("shows a pending-review badge and hides Set primary for a pending AI-generated asset", () => {
    render(
      <AssetManager organizationId="org-1" productId="p1" assets={[pendingReviewAsset]} onAssetsChange={vi.fn()} />
    );

    expect(screen.getByText("Pending Review")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /set primary/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
  });

  it("approves a pending asset and reports the update through onAssetsChange", async () => {
    const approvedAsset: ProductAsset = { ...pendingReviewAsset, approval_status: "approved" };
    vi.mocked(productAssetsApi.approve).mockResolvedValue(approvedAsset);
    const onAssetsChange = vi.fn();
    const user = userEvent.setup();

    render(
      <AssetManager
        organizationId="org-1"
        productId="p1"
        assets={[pendingReviewAsset]}
        onAssetsChange={onAssetsChange}
      />
    );
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(productAssetsApi.approve).toHaveBeenCalledWith("org-1", "p1", "a2");
    await waitFor(() => expect(onAssetsChange).toHaveBeenCalledWith([approvedAsset]));
  });

  it("rejects a pending asset without removing it from the list", async () => {
    const rejectedAsset: ProductAsset = { ...pendingReviewAsset, approval_status: "rejected" };
    vi.mocked(productAssetsApi.reject).mockResolvedValue(rejectedAsset);
    const onAssetsChange = vi.fn();
    const user = userEvent.setup();

    render(
      <AssetManager
        organizationId="org-1"
        productId="p1"
        assets={[pendingReviewAsset]}
        onAssetsChange={onAssetsChange}
      />
    );
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    expect(productAssetsApi.reject).toHaveBeenCalledWith("org-1", "p1", "a2");
    await waitFor(() => expect(onAssetsChange).toHaveBeenCalledWith([rejectedAsset]));
  });

  it("shows an error message when the upload is rejected", async () => {
    vi.mocked(productAssetsApi.upload).mockRejectedValue(
      new ApiError(400, "Only JPEG, PNG, WEBP, and GIF images are supported.")
    );

    const { container } = render(
      <AssetManager organizationId="org-1" productId="p1" assets={[]} onAssetsChange={vi.fn()} />
    );

    const file = new File(["not-an-image"], "fake.jpg", { type: "image/jpeg" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const user = userEvent.setup();
    await user.upload(input, file);

    expect(await screen.findByText(/only jpeg, png, webp, and gif/i)).toBeInTheDocument();
  });

  it("shows a source badge distinguishing uploaded from AI-generated assets", () => {
    render(
      <AssetManager
        organizationId="org-1"
        productId="p1"
        assets={[readyAsset, pendingReviewAsset]}
        onAssetsChange={vi.fn()}
      />
    );

    expect(screen.getByText("Uploaded")).toBeInTheDocument();
    expect(screen.getByText("AI Generated")).toBeInTheDocument();
  });

  it("does not show a Regenerate action for uploaded assets", () => {
    render(
      <AssetManager organizationId="org-1" productId="p1" assets={[readyAsset]} onAssetsChange={vi.fn()} />
    );

    expect(screen.queryByRole("button", { name: /regenerate/i })).not.toBeInTheDocument();
  });

  it("shows the AI-generated prompt for an AI-generated asset behind a toggle", async () => {
    const user = userEvent.setup();
    render(
      <AssetManager organizationId="org-1" productId="p1" assets={[pendingReviewAsset]} onAssetsChange={vi.fn()} />
    );

    expect(screen.queryByText(/a red ceramic mug/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /view ai prompt/i }));

    expect(screen.getByText(/a red ceramic mug/i)).toBeInTheDocument();
  });

  it("regenerates an AI-generated asset and appends the new asset without removing the original", async () => {
    const regeneratedAsset: ProductAsset = {
      ...pendingReviewAsset,
      id: "a3",
      derived_from_asset_id: "a2",
    };
    const regenerateResult: GenerateImageResult = {
      workflow_id: "wf-regen",
      status: "succeeded",
      image_prompt: pendingReviewAsset.image_prompt ?? null,
      error_category: null,
      ai_runs: [],
      asset: regeneratedAsset,
      assets: [regeneratedAsset],
      variations: [
        { index: 0, status: "succeeded", asset: regeneratedAsset, error_category: null, error_message: null },
      ],
    };
    vi.mocked(aiApi.regenerateImage).mockResolvedValue(regenerateResult);
    const onAssetsChange = vi.fn();
    const user = userEvent.setup();

    render(
      <AssetManager
        organizationId="org-1"
        productId="p1"
        assets={[pendingReviewAsset]}
        onAssetsChange={onAssetsChange}
      />
    );
    await user.click(screen.getByRole("button", { name: /^regenerate$/i }));

    expect(aiApi.regenerateImage).toHaveBeenCalledWith("org-1", "p1", "a2");
    await waitFor(() =>
      expect(onAssetsChange).toHaveBeenCalledWith([pendingReviewAsset, regeneratedAsset])
    );
  });

  it("shows an error message when regeneration fails", async () => {
    vi.mocked(aiApi.regenerateImage).mockRejectedValue(new ApiError(500, "Something went wrong."));
    const user = userEvent.setup();

    render(
      <AssetManager
        organizationId="org-1"
        productId="p1"
        assets={[pendingReviewAsset]}
        onAssetsChange={vi.fn()}
      />
    );
    await user.click(screen.getByRole("button", { name: /^regenerate$/i }));

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });
});
