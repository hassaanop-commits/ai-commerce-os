import { apiClient } from "./api-client";
import type { AIRun, GenerateDescriptionResult, GenerateImageResult } from "@/types/ai";
import type { Product } from "@/types/product";

export const aiApi = {
  generateDescription: (orgId: string, productId: string) =>
    apiClient.post<GenerateDescriptionResult>(
      `/organizations/${orgId}/products/${productId}/ai/generate-description`
    ),
  generateImage: (orgId: string, productId: string, prompt: string, variations = 1) =>
    apiClient.post<GenerateImageResult>(`/organizations/${orgId}/products/${productId}/ai/generate-image`, {
      prompt,
      variations,
    }),
  regenerateImage: (orgId: string, productId: string, assetId: string) =>
    apiClient.post<GenerateImageResult>(
      `/organizations/${orgId}/products/${productId}/ai/assets/${assetId}/regenerate`
    ),
  listRuns: (orgId: string, productId: string) =>
    apiClient.get<AIRun[]>(`/organizations/${orgId}/products/${productId}/ai/runs`),
  applyDescription: (orgId: string, productId: string, runId: string) =>
    apiClient.post<Product>(`/organizations/${orgId}/products/${productId}/ai/runs/${runId}/apply-description`),
  applyTitle: (orgId: string, productId: string, runId: string) =>
    apiClient.post<Product>(`/organizations/${orgId}/products/${productId}/ai/runs/${runId}/apply-title`),
  applyTags: (orgId: string, productId: string, runId: string) =>
    apiClient.post<Product>(`/organizations/${orgId}/products/${productId}/ai/runs/${runId}/apply-tags`),
};
