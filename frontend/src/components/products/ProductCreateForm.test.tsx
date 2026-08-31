import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProductCreateForm } from "./ProductCreateForm";
import { OrganizationProvider } from "@/hooks/useOrganization";
import { productsApi } from "@/lib/products-api";
import { ApiError } from "@/lib/api-client";
import type { OrganizationMembership } from "@/types/organization";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: vi.fn() }),
}));

vi.mock("@/lib/products-api", () => ({
  productsApi: { create: vi.fn() },
}));

const org: OrganizationMembership = {
  organization_id: "org-1",
  name: "Acme",
  slug: "acme",
  role_key: "owner",
  role_name: "Owner",
  joined_at: null,
};

function renderForm() {
  return render(
    <OrganizationProvider organizations={[org]}>
      <ProductCreateForm />
    </OrganizationProvider>
  );
}

describe("ProductCreateForm", () => {
  beforeEach(() => {
    vi.mocked(productsApi.create).mockReset();
    pushMock.mockReset();
  });

  it("validates required fields", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /create product/i }));

    expect(await screen.findByText(/title is required/i)).toBeInTheDocument();
    expect(screen.getByText(/sku is required/i)).toBeInTheDocument();
    expect(productsApi.create).not.toHaveBeenCalled();
  });

  it("creates a product and redirects to its detail page", async () => {
    vi.mocked(productsApi.create).mockResolvedValue({
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
    });

    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/title/i), "Widget");
    await user.type(screen.getByLabelText(/sku/i), "SKU-1");
    await user.click(screen.getByRole("button", { name: /create product/i }));

    expect(productsApi.create).toHaveBeenCalledWith(
      "org-1",
      expect.objectContaining({ title: "Widget", sku: "SKU-1" })
    );
    await vi.waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard/products/p1"));
  });

  it("shows a duplicate-SKU message on a 409 response", async () => {
    vi.mocked(productsApi.create).mockRejectedValue(new ApiError(409, "conflict"));

    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/title/i), "Widget");
    await user.type(screen.getByLabelText(/sku/i), "SKU-1");
    await user.click(screen.getByRole("button", { name: /create product/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });
});
