"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useOrganization } from "@/hooks/useOrganization";
import { ApiError } from "@/lib/api-client";
import { productAssetsApi, productsApi } from "@/lib/products-api";
import type { Product, ProductAsset } from "@/types/product";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";
import { StatusBadge } from "@/components/products/StatusBadge";
import { ProductOverview } from "@/components/products/ProductOverview";
import { AssetManager } from "@/components/products/AssetManager";
import { AIStudioPanel } from "@/components/products/AIStudioPanel";
import { ListingsPanel } from "@/components/products/ListingsPanel";
import styles from "./page.module.css";

type Tab = "overview" | "assets" | "ai-studio" | "listings";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "assets", label: "Assets" },
  { key: "ai-studio", label: "AI Studio" },
  { key: "listings", label: "Listings" },
];

export default function ProductDetailPage() {
  const params = useParams<{ productId: string }>();
  const productId = params.productId;
  const { selectedOrganization } = useOrganization();

  const [product, setProduct] = useState<Product | null>(null);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  useEffect(() => {
    if (!selectedOrganization) return;
    let cancelled = false;
    setProduct(null);
    setError(null);

    const orgId = selectedOrganization.organization_id;
    Promise.all([productsApi.get(orgId, productId), productAssetsApi.list(orgId, productId)])
      .then(([productData, assetData]) => {
        if (cancelled) return;
        setProduct(productData);
        setAssets(assetData);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.detail : "Something went wrong loading this product.");
      });

    return () => {
      cancelled = true;
    };
  }, [selectedOrganization, productId]);

  if (error) {
    return (
      <div className={styles.page}>
        <Alert variant="error">{error}</Alert>
      </div>
    );
  }

  if (!product || !selectedOrganization) {
    return (
      <div className={styles.page}>
        <Spinner label="Loading product..." />
      </div>
    );
  }

  const organizationId = selectedOrganization.organization_id;

  return (
    <div className={styles.page}>
      <Link href="/dashboard/products" className={styles.backLink}>
        ← Back to products
      </Link>

      <div className={styles.header}>
        <div>
          <h1>{product.title}</h1>
          <p className={styles.sku}>{product.sku}</p>
        </div>
        <StatusBadge status={product.status} />
      </div>

      <nav className={styles.tabs} aria-label="Product sections">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={[styles.tab, activeTab === tab.key ? styles.tabActive : ""].join(" ")}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className={styles.panel}>
        {activeTab === "overview" ? (
          <ProductOverview organizationId={organizationId} product={product} onSaved={setProduct} />
        ) : null}
        {activeTab === "assets" ? (
          <AssetManager
            organizationId={organizationId}
            productId={product.id}
            assets={assets}
            onAssetsChange={setAssets}
          />
        ) : null}
        {activeTab === "ai-studio" ? (
          <AIStudioPanel
            organizationId={organizationId}
            productId={product.id}
            product={product}
            onProductUpdated={setProduct}
            onAssetChange={(asset) =>
              setAssets((prev) =>
                prev.some((a) => a.id === asset.id) ? prev.map((a) => (a.id === asset.id ? asset : a)) : [...prev, asset]
              )
            }
          />
        ) : null}
        {activeTab === "listings" ? <ListingsPanel organizationId={organizationId} productId={product.id} /> : null}
      </div>
    </div>
  );
}
