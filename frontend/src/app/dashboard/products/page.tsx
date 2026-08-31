"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useOrganization } from "@/hooks/useOrganization";
import { ApiError } from "@/lib/api-client";
import { productsApi } from "@/lib/products-api";
import type { Product } from "@/types/product";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";
import { ProductTable } from "@/components/products/ProductTable";
import buttonStyles from "@/components/ui/Button.module.css";
import styles from "./page.module.css";

export default function ProductsPage() {
  const { selectedOrganization } = useOrganization();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedOrganization) return;
    let cancelled = false;
    setProducts(null);
    setError(null);

    productsApi
      .list(selectedOrganization.organization_id)
      .then((data) => {
        if (!cancelled) setProducts(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.detail : "Something went wrong loading products.");
      });

    return () => {
      cancelled = true;
    };
  }, [selectedOrganization]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1>Products</h1>
          <p className={styles.lede}>Manage your product catalog.</p>
        </div>
        <Link
          href="/dashboard/products/new"
          className={`${buttonStyles.button} ${buttonStyles.primary} ${styles.newButton}`}
        >
          New product
        </Link>
      </div>

      {error ? <Alert variant="error">{error}</Alert> : null}

      {!error && products === null ? <Spinner label="Loading products..." /> : null}

      {!error && products !== null && products.length === 0 ? (
        <div className={styles.emptyState}>
          <h2>No products yet</h2>
          <p>Create your first product to start building your catalog.</p>
          <Link href="/dashboard/products/new" className={`${buttonStyles.button} ${buttonStyles.primary}`}>
            Create a product
          </Link>
        </div>
      ) : null}

      {!error && products !== null && products.length > 0 && selectedOrganization ? (
        <ProductTable products={products} organizationId={selectedOrganization.organization_id} />
      ) : null}
    </div>
  );
}
