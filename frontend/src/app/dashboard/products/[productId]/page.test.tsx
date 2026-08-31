import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProductDetailPage from "./page";
import { OrganizationProvider } from "@/hooks/useOrganization";
import { productsApi, productAssetsApi } from "@/lib/products-api";
import { marketplaceConnectionsApi, listingsApi } from "@/lib/marketplace-api";
import { aiApi } from "@/lib/ai-api";
import type { OrganizationMembership } from "@/types/organization";
import type { Product } from "@/types/product";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ productId: "p1" }),
}));

vi.mock("@/lib/products-api", () => ({
  productsApi: { get: vi.fn(), update: vi.fn() },
  productAssetsApi: { list: vi.fn(), fileUrl: vi.fn(() => "/file") },
}));

vi.mock("@/lib/marketplace-api", () => ({
  marketplaceConnectionsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  listingsApi: { list: vi.fn(), create: vi.fn(), approve: vi.fn(), publish: vi.fn(), retry: vi.fn(), end: vi.fn(), remove: vi.fn() },
}));

vi.mock("@/lib/ai-api", () => ({
  aiApi: { generateDescription: vi.fn(), generateImage: vi.fn(), applyDescription: vi.fn(), listRuns: vi.fn() },
}));

const org: OrganizationMembership = {
  organization_id: "org-1",
  name: "Acme",
  slug: "acme",
  role_key: "owner",
  role_name: "Owner",
  joined_at: null,
};

const product: Product = {
  id: "p1",
  organization_id: "org-1",
  sku: "SKU-1",
  title: "Widget",
  description: null,
  status: "draft",
  price: null,
  currency: "USD",
  metadata: {},
  primary_asset: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderPage() {
  return render(
    <OrganizationProvider organizations={[org]}>
      <ProductDetailPage />
    </OrganizationProvider>
  );
}

describe("ProductDetailPage", () => {
  beforeEach(() => {
    vi.mocked(productsApi.get).mockReset().mockResolvedValue(product);
    vi.mocked(productAssetsApi.list).mockReset().mockResolvedValue([]);
    vi.mocked(marketplaceConnectionsApi.list).mockReset().mockResolvedValue([]);
    vi.mocked(listingsApi.list).mockReset().mockResolvedValue([]);
    vi.mocked(aiApi.listRuns).mockReset().mockResolvedValue([]);
  });

  it("loads and displays the product", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Widget" })).toBeInTheDocument();
    expect(screen.getByText("SKU-1")).toBeInTheDocument();
  });

  it("switches to the Assets tab and shows its empty state", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "Widget" });
    await user.click(screen.getByRole("button", { name: "Assets" }));

    expect(await screen.findByText(/no assets yet/i)).toBeInTheDocument();
  });

  it("shows the AI Studio panel with a generate action", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "Widget" });
    await user.click(screen.getByRole("button", { name: "AI Studio" }));

    expect(await screen.findByRole("heading", { name: "AI Studio" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate description/i })).toBeInTheDocument();
  });

  it("shows the Listings panel with a connect action when there are no connections", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "Widget" });
    await user.click(screen.getByRole("button", { name: "Listings" }));

    expect(await screen.findByRole("heading", { name: "Listings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect manual marketplace/i })).toBeInTheDocument();
  });
});
