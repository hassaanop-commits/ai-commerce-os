export type MarketplaceConnectionStatus = "connected" | "disconnected" | "error" | "expired";
export type ListingStatus = "draft" | "approved" | "publishing" | "active" | "error" | "ended";

export interface MarketplaceConnection {
  id: string;
  marketplace_key: string;
  marketplace_name: string;
  display_name: string | null;
  status: MarketplaceConnectionStatus;
  created_at: string;
}

export interface Listing {
  id: string;
  product_id: string;
  marketplace_connection_id: string;
  marketplace_key: string;
  title: string;
  description: string | null;
  price: string | null;
  currency: string;
  status: ListingStatus;
  external_listing_id: string | null;
  marketplace_url: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}
