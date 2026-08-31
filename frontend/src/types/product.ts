export type ProductStatus = "draft" | "active" | "archived";
export type ProductAssetStatus = "pending" | "processing" | "ready" | "failed";
export type ApprovalStatus = "not_required" | "pending_review" | "approved" | "rejected";

export type ProductAssetSource = "upload" | "ai_generated" | "processed";

export interface ProductAsset {
  id: string;
  product_id: string;
  source: string;
  status: ProductAssetStatus;
  approval_status: ApprovalStatus;
  url: string;
  is_primary: boolean;
  position: number;
  asset_type: string;
  error_message: string | null;
  ai_run_id?: string | null;
  derived_from_asset_id?: string | null;
  image_prompt?: string | null;
  created_at: string;
}

export interface Product {
  id: string;
  organization_id: string;
  sku: string;
  title: string;
  description: string | null;
  status: ProductStatus;
  price: string | null;
  currency: string;
  metadata: Record<string, unknown>;
  primary_asset: ProductAsset | null;
  created_at: string;
  updated_at: string;
}

export interface ProductCreateInput {
  sku: string;
  title: string;
  description?: string;
  price?: number;
  currency?: string;
}

export interface ProductUpdateInput {
  sku?: string;
  title?: string;
  description?: string | null;
  status?: ProductStatus;
  price?: number | null;
  currency?: string;
}

export interface ProductAssetUpdateInput {
  is_primary?: boolean;
  position?: number;
}
