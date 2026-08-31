import { apiClient } from "./api-client";
import type { Listing, MarketplaceConnection } from "@/types/marketplace";

export const marketplaceConnectionsApi = {
  list: (orgId: string) => apiClient.get<MarketplaceConnection[]>(`/organizations/${orgId}/marketplace-connections`),
  create: (orgId: string, marketplaceKey: string, displayName?: string) =>
    apiClient.post<MarketplaceConnection>(`/organizations/${orgId}/marketplace-connections`, {
      marketplace_key: marketplaceKey,
      display_name: displayName,
    }),
  remove: (orgId: string, connectionId: string) =>
    apiClient.delete<MarketplaceConnection>(`/organizations/${orgId}/marketplace-connections/${connectionId}`),
};

export const listingsApi = {
  list: (orgId: string, productId: string) =>
    apiClient.get<Listing[]>(`/organizations/${orgId}/products/${productId}/listings`),
  create: (orgId: string, productId: string, marketplaceConnectionId: string) =>
    apiClient.post<Listing>(`/organizations/${orgId}/products/${productId}/listings`, {
      marketplace_connection_id: marketplaceConnectionId,
    }),
  approve: (orgId: string, productId: string, listingId: string) =>
    apiClient.post<Listing>(`/organizations/${orgId}/products/${productId}/listings/${listingId}/approve`),
  publish: (orgId: string, productId: string, listingId: string) =>
    apiClient.post<Listing>(`/organizations/${orgId}/products/${productId}/listings/${listingId}/publish`),
  retry: (orgId: string, productId: string, listingId: string) =>
    apiClient.post<Listing>(`/organizations/${orgId}/products/${productId}/listings/${listingId}/retry`),
  end: (orgId: string, productId: string, listingId: string) =>
    apiClient.post<Listing>(`/organizations/${orgId}/products/${productId}/listings/${listingId}/end`),
  remove: (orgId: string, productId: string, listingId: string) =>
    apiClient.delete<void>(`/organizations/${orgId}/products/${productId}/listings/${listingId}`),
};
