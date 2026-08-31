import { apiClient } from "./api-client";
import type {
  Product,
  ProductAsset,
  ProductAssetUpdateInput,
  ProductCreateInput,
  ProductUpdateInput,
} from "@/types/product";

// Centralizes every product/product-asset network call so components never
// call fetch() directly -- keeps request shape, error handling, and the
// asset file-URL convention in one place.
export const productsApi = {
  list: (orgId: string) => apiClient.get<Product[]>(`/organizations/${orgId}/products`),
  create: (orgId: string, input: ProductCreateInput) =>
    apiClient.post<Product>(`/organizations/${orgId}/products`, input),
  get: (orgId: string, productId: string) =>
    apiClient.get<Product>(`/organizations/${orgId}/products/${productId}`),
  update: (orgId: string, productId: string, input: ProductUpdateInput) =>
    apiClient.patch<Product>(`/organizations/${orgId}/products/${productId}`, input),
  remove: (orgId: string, productId: string) =>
    apiClient.delete<void>(`/organizations/${orgId}/products/${productId}`),
};

export const productAssetsApi = {
  list: (orgId: string, productId: string) =>
    apiClient.get<ProductAsset[]>(`/organizations/${orgId}/products/${productId}/assets`),
  upload: (
    orgId: string,
    productId: string,
    file: File,
    isPrimary: boolean,
    onProgress?: (percent: number) => void
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("is_primary", String(isPrimary));
    return apiClient.uploadWithProgress<ProductAsset>(
      `/organizations/${orgId}/products/${productId}/assets`,
      formData,
      onProgress
    );
  },
  update: (orgId: string, productId: string, assetId: string, input: ProductAssetUpdateInput) =>
    apiClient.patch<ProductAsset>(
      `/organizations/${orgId}/products/${productId}/assets/${assetId}`,
      input
    ),
  remove: (orgId: string, productId: string, assetId: string) =>
    apiClient.delete<void>(`/organizations/${orgId}/products/${productId}/assets/${assetId}`),
  approve: (orgId: string, productId: string, assetId: string) =>
    apiClient.post<ProductAsset>(`/organizations/${orgId}/products/${productId}/assets/${assetId}/approve`),
  reject: (orgId: string, productId: string, assetId: string) =>
    apiClient.post<ProductAsset>(`/organizations/${orgId}/products/${productId}/assets/${assetId}/reject`),
  fileUrl: (orgId: string, productId: string, assetId: string) =>
    `/api/v1/organizations/${orgId}/products/${productId}/assets/${assetId}/file`,
};
