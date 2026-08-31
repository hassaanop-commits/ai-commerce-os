import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import ProductsPage from "./page";
import { OrganizationProvider } from "@/hooks/useOrganization";
import { productsApi, productAssetsApi } from "@/lib/products-api";
import { ApiError } from "@/lib/api-client";
import type { OrganizationMembership } from "@/types/organization";

vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: ReactNode; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/products-api", () => ({
  productsApi: { list: vi.fn() },
  productAssetsApi: { fileUrl: vi.fn(() => "/fake-file-url") },
}));

const org: OrganizationMembership = {
  organization_id: "org-1",
  name: "Acme",
  slug: "acme",
  role_key: "owner",
  role_name: "Owner",
  joined_at: null,
};

function renderWithOrg() {
  return render(
    <OrganizationProvider organizations={[org]}>
      <ProductsPage />
    </OrganizationProvider>
  );
}

describe("ProductsPage", () => {
  beforeEach(() => {
    vi.mocked(productsApi.list).mockReset();
    vi.mocked(productAssetsApi.fileUrl).mockReset().mockReturnValue("/fake-file-url");
  });

  it("shows a loading state while fetching", () => {
    vi.mocked(productsApi.list).mockReturnValue(new Promise(() => {}));

    renderWithOrg();

    expect(screen.getByText(/loading products/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no products", async () => {
    vi.mocked(productsApi.list).mockResolvedValue([]);

    renderWithOrg();

    expect(await screen.findByText(/no products yet/i)).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(productsApi.list).mockRejectedValue(new ApiError(500, "Server error."));

    renderWithOrg();

    expect(await screen.findByText(/server error/i)).toBeInTheDocument();
  });

  it("renders the product list once loaded", async () => {
    vi.mocked(productsApi.list).mockResolvedValue([
      {
        id: "p1",
        organization_id: "org-1",
        sku: "SKU-1",
        title: "Widget",
        description: null,
        status: "draft",
        price: "9.99",
        currency: "USD",
        metadata: {},
        primary_asset: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);

    renderWithOrg();

    expect(await screen.findByText("Widget")).toBeInTheDocument();
    expect(screen.getByText("SKU-1")).toBeInTheDocument();
  });
});
