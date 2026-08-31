import type { ProductAsset } from "./product";

export type AIRunStatus = "pending" | "running" | "succeeded" | "failed";

export interface AIRun {
  id: string;
  run_type: string;
  provider: string;
  model: string;
  status: AIRunStatus;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface GenerateDescriptionResult {
  workflow_id: string;
  status: "succeeded" | "failed";
  analysis: string | null;
  generated_description: string | null;
  generated_title: string | null;
  generated_tags: string[] | null;
  error_category: string | null;
  ai_runs: AIRun[];
}

export interface GenerateImageVariationResult {
  index: number;
  status: "succeeded" | "failed";
  asset: ProductAsset | null;
  error_category: string | null;
  error_message: string | null;
}

export interface GenerateImageResult {
  workflow_id: string;
  status: "succeeded" | "failed";
  image_prompt: string | null;
  error_category: string | null;
  ai_runs: AIRun[];
  asset: ProductAsset | null;
  assets: ProductAsset[];
  variations: GenerateImageVariationResult[];
}
