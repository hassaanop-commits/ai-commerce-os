import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ListingsPanel } from "./ListingsPanel";
import { listingsApi, marketplaceConnectionsApi } from "@/lib/marketplace-api";
import { ApiError } from "@/lib/api-client";
import type { Listing, MarketplaceConnection } from "@/types/marketplace";

vi.mock("@/lib/marketplace-api", () => ({
  marketplaceConnectionsApi: {
    list: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
  },
  listingsApi: {
    list: vi.fn(),
    create: vi.fn(),
    approve: vi.fn(),
    publish: vi.fn(),
    retry: vi.fn(),
    end: vi.fn(),
    remove: vi.fn(),
  },
}));

const connection: MarketplaceConnection = {
  id: "conn-1",
  marketplace_key: "manual",
  marketplace_name: "Manual (test)",
  display_name: "Test Store",
  status: "connected",
  created_at: "2026-01-01T00:00:00Z",
};

const draftListing: Listing = {
  id: "listing-1",
  product_id: "p1",
  marketplace_connection_id: "conn-1",
  marketplace_key: "manual",
  title: "Widget",
  description: null,
  price: null,
  currency: "USD",
  status: "draft",
  external_listing_id: null,
  marketplace_url: null,
  last_error: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function mockLoaded(connections: MarketplaceConnection[], listings: Listing[]) {
  vi.mocked(marketplaceConnectionsApi.list).mockResolvedValue(connections);
  vi.mocked(listingsApi.list).mockResolvedValue(listings);
}

describe("ListingsPanel", () => {
  beforeEach(() => {
    vi.mocked(marketplaceConnectionsApi.list).mockReset();
    vi.mocked(marketplaceConnectionsApi.create).mockReset();
    vi.mocked(listingsApi.list).mockReset();
    vi.mocked(listingsApi.create).mockReset();
    vi.mocked(listingsApi.approve).mockReset();
    vi.mocked(listingsApi.publish).mockReset();
    vi.mocked(listingsApi.retry).mockReset();
    vi.mocked(listingsApi.end).mockReset();
    vi.mocked(listingsApi.remove).mockReset();
  });

  it("shows a loading state while fetching", async () => {
    let resolveConnections!: (value: MarketplaceConnection[]) => void;
    vi.mocked(marketplaceConnectionsApi.list).mockReturnValue(
      new Promise((resolve) => {
        resolveConnections = resolve;
      })
    );
    vi.mocked(listingsApi.list).mockResolvedValue([]);

    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    expect(screen.getByText(/loading listings/i)).toBeInTheDocument();
    resolveConnections([]);
    await waitFor(() => expect(screen.queryByText(/loading listings/i)).not.toBeInTheDocument());
  });

  it("shows a connect action when there are no connections", async () => {
    mockLoaded([], []);
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    expect(await screen.findByRole("button", { name: /connect manual marketplace/i })).toBeInTheDocument();
    expect(screen.getByText(/no marketplace connections yet/i)).toBeInTheDocument();
  });

  it("connects a manual marketplace", async () => {
    mockLoaded([], []);
    vi.mocked(marketplaceConnectionsApi.create).mockResolvedValue(connection);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /connect manual marketplace/i }));

    expect(marketplaceConnectionsApi.create).toHaveBeenCalledWith("org-1", "manual", "Manual (test)");
    expect(await screen.findByRole("button", { name: /create draft listing/i })).toBeInTheDocument();
  });

  it("creates a draft listing against the selected connection", async () => {
    mockLoaded([connection], []);
    vi.mocked(listingsApi.create).mockResolvedValue(draftListing);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /create draft listing/i }));

    expect(listingsApi.create).toHaveBeenCalledWith("org-1", "p1", "conn-1");
    expect(await screen.findByText("Widget")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  it("approves a draft listing, revealing the publish action", async () => {
    mockLoaded([connection], [draftListing]);
    const approved: Listing = { ...draftListing, status: "approved" };
    vi.mocked(listingsApi.approve).mockResolvedValue(approved);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /^approve$/i }));

    expect(listingsApi.approve).toHaveBeenCalledWith("org-1", "p1", "listing-1");
    expect(await screen.findByRole("button", { name: /^publish$/i })).toBeInTheDocument();
  });

  it("publishes an approved listing and shows the marketplace url", async () => {
    const approvedListing: Listing = { ...draftListing, status: "approved" };
    mockLoaded([connection], [approvedListing]);
    const active: Listing = {
      ...approvedListing,
      status: "active",
      external_listing_id: "manual-abc123",
      marketplace_url: "https://manual.test/listings/manual-abc123",
    };
    vi.mocked(listingsApi.publish).mockResolvedValue(active);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /^publish$/i }));

    expect(listingsApi.publish).toHaveBeenCalledWith("org-1", "p1", "listing-1");
    expect(await screen.findByText("https://manual.test/listings/manual-abc123")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /end listing/i })).toBeInTheDocument();
  });

  it("shows a retry action and error message for a listing in error status", async () => {
    const erroredListing: Listing = { ...draftListing, status: "error", last_error: "marketplace_error" };
    mockLoaded([connection], [erroredListing]);
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    expect(await screen.findByRole("button", { name: /^retry$/i })).toBeInTheDocument();
    expect(screen.getByText(/publishing failed/i)).toBeInTheDocument();
  });

  it("retries a failed listing back to active", async () => {
    const erroredListing: Listing = { ...draftListing, status: "error", last_error: "marketplace_error" };
    mockLoaded([connection], [erroredListing]);
    const active: Listing = { ...erroredListing, status: "active", last_error: null, external_listing_id: "manual-xyz" };
    vi.mocked(listingsApi.retry).mockResolvedValue(active);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /^retry$/i }));

    expect(listingsApi.retry).toHaveBeenCalledWith("org-1", "p1", "listing-1");
    await waitFor(() => expect(screen.queryByRole("button", { name: /^retry$/i })).not.toBeInTheDocument());
  });

  it("ends an active listing", async () => {
    const activeListing: Listing = { ...draftListing, status: "active", external_listing_id: "manual-abc" };
    mockLoaded([connection], [activeListing]);
    const ended: Listing = { ...activeListing, status: "ended" };
    vi.mocked(listingsApi.end).mockResolvedValue(ended);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /end listing/i }));

    expect(listingsApi.end).toHaveBeenCalledWith("org-1", "p1", "listing-1");
    await waitFor(() => expect(screen.queryByRole("button", { name: /end listing/i })).not.toBeInTheDocument());
  });

  it("deletes a draft listing", async () => {
    mockLoaded([connection], [draftListing]);
    vi.mocked(listingsApi.remove).mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /^delete$/i }));

    expect(listingsApi.remove).toHaveBeenCalledWith("org-1", "p1", "listing-1");
    await waitFor(() => expect(screen.queryByText("Widget")).not.toBeInTheDocument());
  });

  it("shows an error message when an action fails", async () => {
    mockLoaded([connection], [draftListing]);
    vi.mocked(listingsApi.approve).mockRejectedValue(new ApiError(409, "This listing is not a draft."));
    const user = userEvent.setup();
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    await user.click(await screen.findByRole("button", { name: /^approve$/i }));

    expect(await screen.findByText(/this listing is not a draft/i)).toBeInTheDocument();
  });

  it("shows an error state when the initial load fails", async () => {
    vi.mocked(marketplaceConnectionsApi.list).mockRejectedValue(new ApiError(500, "Something went wrong."));
    vi.mocked(listingsApi.list).mockResolvedValue([]);
    render(<ListingsPanel organizationId="org-1" productId="p1" />);

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });
});
