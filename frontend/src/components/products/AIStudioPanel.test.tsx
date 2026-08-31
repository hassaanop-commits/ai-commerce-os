import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AIStudioPanel } from "./AIStudioPanel";
import { aiApi } from "@/lib/ai-api";
import { productAssetsApi } from "@/lib/products-api";
import { ApiError } from "@/lib/api-client";
import type { AIRun, GenerateDescriptionResult, GenerateImageResult } from "@/types/ai";
import type { Product, ProductAsset } from "@/types/product";

vi.mock("@/lib/ai-api", () => ({
  aiApi: {
    generateDescription: vi.fn(),
    generateImage: vi.fn(),
    applyDescription: vi.fn(),
    applyTitle: vi.fn(),
    applyTags: vi.fn(),
    listRuns: vi.fn(),
  },
}));

vi.mock("@/lib/products-api", () => ({
  productAssetsApi: {
    approve: vi.fn(),
    reject: vi.fn(),
    fileUrl: vi.fn((_orgId: string, _productId: string, assetId: string) => `/file/${assetId}`),
  },
}));

const analyzeRun: AIRun = {
  id: "run-analyze",
  run_type: "product_content.analyze",
  provider: "mock",
  model: "mock-model",
  status: "succeeded",
  input_tokens: 10,
  output_tokens: 10,
  cost_usd: "0.000000",
  error_message: null,
  started_at: "2026-01-01T00:00:00Z",
  completed_at: "2026-01-01T00:00:01Z",
  created_at: "2026-01-01T00:00:00Z",
  metadata: { workflow_id: "wf-1" },
};

const describeRun: AIRun = {
  id: "run-describe",
  run_type: "product_content.generate_description",
  provider: "anthropic",
  model: "claude-sonnet-5",
  status: "succeeded",
  input_tokens: 120,
  output_tokens: 64,
  cost_usd: "0.001320",
  error_message: null,
  started_at: "2026-01-01T00:00:01Z",
  completed_at: "2026-01-01T00:00:02Z",
  created_at: "2026-01-01T00:00:01Z",
  metadata: { workflow_id: "wf-1" },
};

const titleRun: AIRun = {
  id: "run-title",
  run_type: "product_content.generate_title",
  provider: "anthropic",
  model: "claude-haiku-4-5-20251001",
  status: "succeeded",
  input_tokens: 40,
  output_tokens: 8,
  cost_usd: "0.000064",
  error_message: null,
  started_at: "2026-01-01T00:00:02Z",
  completed_at: "2026-01-01T00:00:03Z",
  created_at: "2026-01-01T00:00:02Z",
  metadata: { workflow_id: "wf-1" },
};

const tagsRun: AIRun = {
  id: "run-tags",
  run_type: "product_content.generate_tags",
  provider: "anthropic",
  model: "claude-haiku-4-5-20251001",
  status: "succeeded",
  input_tokens: 45,
  output_tokens: 12,
  cost_usd: "0.000096",
  error_message: null,
  started_at: "2026-01-01T00:00:03Z",
  completed_at: "2026-01-01T00:00:04Z",
  created_at: "2026-01-01T00:00:03Z",
  metadata: { workflow_id: "wf-1" },
};

const successResult: GenerateDescriptionResult = {
  workflow_id: "wf-1",
  status: "succeeded",
  analysis: "The product has a title and SKU but no description.",
  generated_description: "A sleek wireless mouse built for comfort.",
  generated_title: "Ergonomic Wireless Mouse",
  generated_tags: ["wireless", "mouse", "ergonomic", "bluetooth"],
  error_category: null,
  ai_runs: [analyzeRun, describeRun, titleRun, tagsRun],
};

const pendingAsset: ProductAsset = {
  id: "asset-1",
  product_id: "p1",
  source: "ai_generated",
  status: "ready",
  approval_status: "pending_review",
  url: "/file/asset-1",
  is_primary: false,
  position: 1,
  asset_type: "image",
  error_message: null,
  ai_run_id: "run-generate",
  derived_from_asset_id: null,
  image_prompt: "A red ceramic mug on a white studio background.",
  created_at: "2026-01-01T00:00:00Z",
};

const successImageResult: GenerateImageResult = {
  workflow_id: "wf-2",
  status: "succeeded",
  image_prompt: "A red ceramic mug on a white studio background.",
  error_category: null,
  ai_runs: [
    {
      id: "run-craft",
      run_type: "product_image.craft_prompt",
      provider: "mock",
      model: "mock-model",
      status: "succeeded",
      input_tokens: 10,
      output_tokens: 10,
      cost_usd: "0.000000",
      error_message: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:01Z",
      created_at: "2026-01-01T00:00:00Z",
      metadata: { workflow_id: "wf-2" },
    },
    {
      id: "run-generate",
      run_type: "product_image.generate",
      provider: "mock",
      model: "mock-image-model",
      status: "succeeded",
      input_tokens: 0,
      output_tokens: 0,
      cost_usd: "0.000000",
      error_message: null,
      started_at: "2026-01-01T00:00:01Z",
      completed_at: "2026-01-01T00:00:02Z",
      created_at: "2026-01-01T00:00:01Z",
      metadata: { workflow_id: "wf-2" },
    },
  ],
  asset: pendingAsset,
  assets: [pendingAsset],
  variations: [
    { index: 0, status: "succeeded", asset: pendingAsset, error_category: null, error_message: null },
  ],
};

const product: Product = {
  id: "p1",
  organization_id: "org-1",
  sku: "SKU-1",
  title: "Widget",
  description: "An existing hand-written description.",
  status: "draft",
  price: null,
  currency: "USD",
  metadata: {},
  primary_asset: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderPanel(overrides: Partial<React.ComponentProps<typeof AIStudioPanel>> = {}) {
  return render(
    <AIStudioPanel
      organizationId="org-1"
      productId="p1"
      product={product}
      onProductUpdated={vi.fn()}
      {...overrides}
    />
  );
}

describe("AIStudioPanel", () => {
  beforeEach(() => {
    vi.mocked(aiApi.generateDescription).mockReset();
    vi.mocked(aiApi.applyDescription).mockReset();
    vi.mocked(aiApi.applyTitle).mockReset();
    vi.mocked(aiApi.applyTags).mockReset();
    vi.mocked(aiApi.generateImage).mockReset();
    vi.mocked(aiApi.listRuns).mockReset().mockResolvedValue([]);
    vi.mocked(productAssetsApi.approve).mockReset();
    vi.mocked(productAssetsApi.reject).mockReset();
  });

  it("shows the current product title, description, and tags", async () => {
    renderPanel();

    expect(await screen.findByText("Widget")).toBeInTheDocument();
    expect(screen.getByText("An existing hand-written description.")).toBeInTheDocument();
    expect(screen.getByText(/no tags yet/i)).toBeInTheDocument();
  });

  it("shows existing tags from product metadata", async () => {
    renderPanel({ product: { ...product, metadata: { tags: ["existing", "tag"] } } });

    expect(await screen.findByText("existing, tag")).toBeInTheDocument();
  });

  it("shows a loading state while generating", async () => {
    let resolveFn!: (value: GenerateDescriptionResult) => void;
    vi.mocked(aiApi.generateDescription).mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve;
      })
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));

    expect(screen.getByRole("status")).toHaveTextContent(/analyzing product/i);

    resolveFn(successResult);
    await waitFor(() => expect(screen.queryByText(/analyzing product/i)).not.toBeInTheDocument());
  });

  it("shows the generated draft distinctly from the current description", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));

    expect(await screen.findByText(/a sleek wireless mouse/i)).toBeInTheDocument();
    expect(screen.getByText(/ai draft — not yet applied/i)).toBeInTheDocument();
    expect(screen.getByText("An existing hand-written description.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply to product/i })).toBeInTheDocument();
  });

  it("shows provider, model, and cost for the draft", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await screen.findByText(/a sleek wireless mouse/i);

    expect(screen.getAllByText("anthropic", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText("claude-sonnet-5", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("$0.001320", { exact: false })).toBeInTheDocument();
  });

  it("relabels the action to Regenerate once a draft exists", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const user = userEvent.setup();
    renderPanel();

    expect(screen.getByRole("button", { name: /^generate description$/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^generate description$/i }));
    await screen.findByText(/a sleek wireless mouse/i);

    expect(screen.getByRole("button", { name: /^regenerate$/i })).toBeInTheDocument();
  });

  it("regenerating creates a fresh draft without needing a page reload", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValueOnce(successResult).mockResolvedValueOnce({
      ...successResult,
      workflow_id: "wf-3",
      generated_description: "An even better description.",
      ai_runs: [
        { ...analyzeRun, id: "run-analyze-2" },
        { ...describeRun, id: "run-describe-2" },
      ],
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /^generate description$/i }));
    await screen.findByText(/a sleek wireless mouse/i);

    await user.click(screen.getByRole("button", { name: /^regenerate$/i }));

    expect(await screen.findByText(/an even better description/i)).toBeInTheDocument();
    expect(aiApi.generateDescription).toHaveBeenCalledTimes(2);
  });

  it("shows an error state when generation fails at the provider", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue({
      ...successResult,
      status: "failed",
      generated_description: null,
      analysis: null,
      error_category: "provider_timeout",
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));

    expect(await screen.findByText(/timed out/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply to product/i })).not.toBeInTheDocument();
  });

  it("shows an error state when the generate request itself fails", async () => {
    vi.mocked(aiApi.generateDescription).mockRejectedValue(new ApiError(500, "Something went wrong."));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("applies the draft and reports the updated product", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const updatedProduct: Product = { ...product, description: successResult.generated_description };
    vi.mocked(aiApi.applyDescription).mockResolvedValue(updatedProduct);
    const onProductUpdated = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onProductUpdated });

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await screen.findByRole("button", { name: /apply to product/i });
    await user.click(screen.getByRole("button", { name: /apply to product/i }));

    await waitFor(() => expect(onProductUpdated).toHaveBeenCalledWith(updatedProduct));
    expect(await screen.findByText(/applied to the product/i)).toBeInTheDocument();
    expect(aiApi.applyDescription).toHaveBeenCalledWith("org-1", "p1", "run-describe");
  });

  it("shows an error state when apply fails", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    vi.mocked(aiApi.applyDescription).mockRejectedValue(
      new ApiError(409, "This AI run has no applicable description.")
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await screen.findByRole("button", { name: /apply to product/i });
    await user.click(screen.getByRole("button", { name: /apply to product/i }));

    expect(await screen.findByText(/no applicable description/i)).toBeInTheDocument();
  });

  it("shows the generated title and tags drafts with their own apply actions", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));

    expect(await screen.findByText("Ergonomic Wireless Mouse")).toBeInTheDocument();
    expect(screen.getByText("wireless, mouse, ergonomic, bluetooth")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply title/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply tags/i })).toBeInTheDocument();
  });

  it("applies the title independently of the description", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const updatedProduct: Product = { ...product, title: successResult.generated_title! };
    vi.mocked(aiApi.applyTitle).mockResolvedValue(updatedProduct);
    const onProductUpdated = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onProductUpdated });

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await user.click(await screen.findByRole("button", { name: /apply title/i }));

    expect(aiApi.applyTitle).toHaveBeenCalledWith("org-1", "p1", "run-title");
    await waitFor(() => expect(onProductUpdated).toHaveBeenCalledWith(updatedProduct));
    // Description apply is untouched -- only the title action fired.
    expect(aiApi.applyDescription).not.toHaveBeenCalled();
  });

  it("shows an error state when applying the title fails", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    vi.mocked(aiApi.applyTitle).mockRejectedValue(new ApiError(409, "This AI run has no applicable title."));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await user.click(await screen.findByRole("button", { name: /apply title/i }));

    expect(await screen.findByText(/no applicable title/i)).toBeInTheDocument();
  });

  it("applies tags independently of the description", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const updatedProduct: Product = { ...product, metadata: { tags: successResult.generated_tags } };
    vi.mocked(aiApi.applyTags).mockResolvedValue(updatedProduct);
    const onProductUpdated = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onProductUpdated });

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await user.click(await screen.findByRole("button", { name: /apply tags/i }));

    expect(aiApi.applyTags).toHaveBeenCalledWith("org-1", "p1", "run-tags");
    await waitFor(() => expect(onProductUpdated).toHaveBeenCalledWith(updatedProduct));
  });

  it("shows an error state when applying tags fails", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    vi.mocked(aiApi.applyTags).mockRejectedValue(new ApiError(409, "This AI run has no applicable tags."));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await user.click(await screen.findByRole("button", { name: /apply tags/i }));

    expect(await screen.findByText(/no applicable tags/i)).toBeInTheDocument();
  });

  it("shows provider and model for the title and tags drafts", async () => {
    vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: /generate description/i }));
    await screen.findByText("Ergonomic Wireless Mouse");

    expect(screen.getAllByText("claude-haiku-4-5-20251001", { exact: false }).length).toBeGreaterThan(0);
  });

  it("shows a loading state while generating an image", async () => {
    let resolveFn!: (value: GenerateImageResult) => void;
    vi.mocked(aiApi.generateImage).mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve;
      })
    );
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
    await user.click(screen.getByRole("button", { name: /generate image/i }));

    expect(screen.getByRole("status")).toHaveTextContent(/generating the image/i);

    resolveFn(successImageResult);
    await waitFor(() => expect(screen.queryByText(/generating the image/i)).not.toBeInTheDocument());
  });

  it("shows the generated image pending review with approve/reject actions", async () => {
    vi.mocked(aiApi.generateImage).mockResolvedValue(successImageResult);
    const onAssetChange = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onAssetChange });

    await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
    await user.click(screen.getByRole("button", { name: /generate image/i }));

    expect(await screen.findByText(/pending review/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
    expect(onAssetChange).toHaveBeenCalledWith(pendingAsset);
  });

  it("shows an error state when image generation fails at the provider", async () => {
    vi.mocked(aiApi.generateImage).mockResolvedValue({
      ...successImageResult,
      status: "failed",
      asset: null,
      assets: [],
      variations: [],
      image_prompt: null,
      error_category: "content_policy_violation",
    });
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
    await user.click(screen.getByRole("button", { name: /generate image/i }));

    expect(await screen.findByText(/content moderation/i)).toBeInTheDocument();
  });

  it("shows an error state when the image generate request itself fails", async () => {
    vi.mocked(aiApi.generateImage).mockRejectedValue(new ApiError(500, "Something went wrong."));
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
    await user.click(screen.getByRole("button", { name: /generate image/i }));

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("approves the generated image", async () => {
    vi.mocked(aiApi.generateImage).mockResolvedValue(successImageResult);
    const approvedAsset: ProductAsset = { ...pendingAsset, approval_status: "approved" };
    vi.mocked(productAssetsApi.approve).mockResolvedValue(approvedAsset);
    const onAssetChange = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onAssetChange });

    await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
    await user.click(screen.getByRole("button", { name: /generate image/i }));
    await screen.findByRole("button", { name: /^approve$/i });
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(productAssetsApi.approve).toHaveBeenCalledWith("org-1", "p1", "asset-1");
    await waitFor(() => expect(onAssetChange).toHaveBeenCalledWith(approvedAsset));
    expect(await screen.findByText(/can now be set as the primary image/i)).toBeInTheDocument();
  });

  it("rejects the generated image", async () => {
    vi.mocked(aiApi.generateImage).mockResolvedValue(successImageResult);
    const rejectedAsset: ProductAsset = { ...pendingAsset, approval_status: "rejected" };
    vi.mocked(productAssetsApi.reject).mockResolvedValue(rejectedAsset);
    const onAssetChange = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onAssetChange });

    await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
    await user.click(screen.getByRole("button", { name: /generate image/i }));
    await screen.findByRole("button", { name: /^reject$/i });
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    expect(productAssetsApi.reject).toHaveBeenCalledWith("org-1", "p1", "asset-1");
    await waitFor(() => expect(onAssetChange).toHaveBeenCalledWith(rejectedAsset));
    expect(await screen.findByText(/stays visible in the assets tab/i)).toBeInTheDocument();
  });

  describe("image variations", () => {
    const secondAsset: ProductAsset = { ...pendingAsset, id: "asset-2", ai_run_id: "run-generate-2" };
    const thirdAsset: ProductAsset = { ...pendingAsset, id: "asset-3", ai_run_id: "run-generate-3" };

    function succeeded(index: number, asset: ProductAsset): GenerateImageResult["variations"][number] {
      return { index, status: "succeeded", asset, error_category: null, error_message: null };
    }
    function failed(index: number, category: string, message: string): GenerateImageResult["variations"][number] {
      return { index, status: "failed", asset: null, error_category: category, error_message: message };
    }

    it("requests the selected number of variations", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        assets: [pendingAsset, secondAsset, thirdAsset],
        variations: [succeeded(0, pendingAsset), succeeded(1, secondAsset), succeeded(2, thirdAsset)],
      });
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.selectOptions(screen.getByLabelText(/variations/i), "3");
      await user.click(screen.getByRole("button", { name: /generate 3 variations/i }));

      expect(aiApi.generateImage).toHaveBeenCalledWith("org-1", "p1", "a red mug", 3);
    });

    it("renders each generated variation with its own approve/reject actions", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        assets: [pendingAsset, secondAsset],
        variations: [succeeded(0, pendingAsset), succeeded(1, secondAsset)],
      });
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.click(screen.getByRole("button", { name: /generate image/i }));

      expect(await screen.findAllByRole("button", { name: /^approve$/i })).toHaveLength(2);
      expect(screen.getAllByRole("button", { name: /^reject$/i })).toHaveLength(2);
    });

    it("approving one variation does not affect the other", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        assets: [pendingAsset, secondAsset],
        variations: [succeeded(0, pendingAsset), succeeded(1, secondAsset)],
      });
      const approvedAsset: ProductAsset = { ...pendingAsset, approval_status: "approved" };
      vi.mocked(productAssetsApi.approve).mockResolvedValue(approvedAsset);
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.click(screen.getByRole("button", { name: /generate image/i }));
      const approveButtons = await screen.findAllByRole("button", { name: /^approve$/i });
      await user.click(approveButtons[0]);

      expect(productAssetsApi.approve).toHaveBeenCalledWith("org-1", "p1", "asset-1");
      expect(productAssetsApi.approve).not.toHaveBeenCalledWith("org-1", "p1", "asset-2");
      await waitFor(() => expect(screen.getAllByRole("button", { name: /^approve$/i })).toHaveLength(1));
    });

    it("shows a partial-failure notice when fewer variations succeed than requested", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        assets: [pendingAsset],
        variations: [
          succeeded(0, pendingAsset),
          failed(1, "provider_rate_limited", "AI service is temporarily rate limited. Please try again."),
          failed(2, "content_policy_violation", "The request was rejected by content moderation."),
        ],
      });
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.selectOptions(screen.getByLabelText(/variations/i), "3");
      await user.click(screen.getByRole("button", { name: /generate 3 variations/i }));

      expect(await screen.findByText(/1 of 3 variations generated successfully/i)).toBeInTheDocument();
    });

    it("shows a distinct failed-slot indicator with the reason for each failed variation", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        assets: [pendingAsset],
        variations: [
          succeeded(0, pendingAsset),
          failed(1, "provider_rate_limited", "AI service is temporarily rate limited. Please try again."),
          failed(2, "content_policy_violation", "The request was rejected by content moderation."),
        ],
      });
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.selectOptions(screen.getByLabelText(/variations/i), "3");
      await user.click(screen.getByRole("button", { name: /generate 3 variations/i }));

      expect(await screen.findByText(/variation 2 failed/i)).toBeInTheDocument();
      expect(screen.getByText(/temporarily rate limited/i)).toBeInTheDocument();
      expect(screen.getByText(/variation 3 failed/i)).toBeInTheDocument();
      expect(screen.getByText(/rejected by content moderation/i)).toBeInTheDocument();
      // Only the succeeded slot gets review actions.
      expect(screen.getAllByRole("button", { name: /^approve$/i })).toHaveLength(1);
    });

    it("shows per-variation failure detail even when every variation fails", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        status: "failed",
        asset: null,
        assets: [],
        error_category: "provider_error",
        variations: [
          failed(0, "provider_error", "The AI provider returned an error. Please try again."),
          failed(1, "provider_timeout", "The AI provider timed out. Please try again."),
        ],
      });
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.selectOptions(screen.getByLabelText(/variations/i), "2");
      await user.click(screen.getByRole("button", { name: /generate 2 variations/i }));

      expect(await screen.findByText(/variation 1 failed/i)).toBeInTheDocument();
      expect(screen.getByText(/variation 2 failed/i)).toBeInTheDocument();
      expect(screen.getByText(/the ai provider timed out/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    });

    it("never renders raw provider exception text, only the sanitized message", async () => {
      vi.mocked(aiApi.generateImage).mockResolvedValue({
        ...successImageResult,
        assets: [pendingAsset],
        variations: [
          succeeded(0, pendingAsset),
          failed(1, "provider_error", "The AI provider returned an error. Please try again."),
        ],
      });
      const user = userEvent.setup();
      renderPanel();

      await user.type(screen.getByLabelText(/describe the image/i), "a red mug");
      await user.selectOptions(screen.getByLabelText(/variations/i), "2");
      await user.click(screen.getByRole("button", { name: /generate 2 variations/i }));

      await screen.findByText(/variation 2 failed/i);
      expect(screen.queryByText(/traceback|stack trace|Exception:|httpx\./i)).not.toBeInTheDocument();
    });
  });

  describe("generation history", () => {
    it("shows a loading state while fetching history", async () => {
      let resolveFn!: (value: AIRun[]) => void;
      vi.mocked(aiApi.listRuns).mockReturnValue(
        new Promise((resolve) => {
          resolveFn = resolve;
        })
      );
      renderPanel();

      expect(screen.getByText(/loading history/i)).toBeInTheDocument();

      resolveFn([]);
      await waitFor(() => expect(screen.queryByText(/loading history/i)).not.toBeInTheDocument());
    });

    it("shows an empty state when there is no history yet", async () => {
      vi.mocked(aiApi.listRuns).mockResolvedValue([]);
      renderPanel();

      expect(await screen.findByText(/no ai generations yet/i)).toBeInTheDocument();
    });

    it("shows successful runs with provider, model, tokens, and cost", async () => {
      vi.mocked(aiApi.listRuns).mockResolvedValue([describeRun]);
      renderPanel();

      expect(await screen.findByText(/description generation/i)).toBeInTheDocument();
      expect(screen.getByText(/120 in \/ 64 out tokens/i)).toBeInTheDocument();
      expect(screen.getByText(/\$0\.001320/)).toBeInTheDocument();
    });

    it("shows failed runs with a human-readable failure reason", async () => {
      const failedRun: AIRun = {
        ...describeRun,
        id: "run-failed",
        status: "failed",
        error_message: "provider_rate_limited",
      };
      vi.mocked(aiApi.listRuns).mockResolvedValue([failedRun]);
      renderPanel();

      expect(await screen.findByText(/description generation/i)).toBeInTheDocument();
      expect(screen.getByText(/busy right now/i)).toBeInTheDocument();
    });

    it("shows retry count when a run required retries", async () => {
      const retriedRun: AIRun = { ...describeRun, metadata: { workflow_id: "wf-1", retries: 2, attempts: 3 } };
      vi.mocked(aiApi.listRuns).mockResolvedValue([retriedRun]);
      renderPanel();

      expect(await screen.findByText(/retried 2×/i)).toBeInTheDocument();
    });

    it("shows an error state when history fails to load", async () => {
      vi.mocked(aiApi.listRuns).mockRejectedValue(new ApiError(500, "Could not load history."));
      renderPanel();

      expect(await screen.findByText(/could not load history/i)).toBeInTheDocument();
    });

    it("refreshes history after a new generation", async () => {
      vi.mocked(aiApi.listRuns).mockResolvedValueOnce([]).mockResolvedValueOnce([analyzeRun, describeRun]);
      vi.mocked(aiApi.generateDescription).mockResolvedValue(successResult);
      const user = userEvent.setup();
      renderPanel();

      await screen.findByText(/no ai generations yet/i);

      await user.click(screen.getByRole("button", { name: /generate description/i }));

      await waitFor(() => expect(aiApi.listRuns).toHaveBeenCalledTimes(2));
      expect(await screen.findByText(/description generation/i)).toBeInTheDocument();
    });
  });
});
