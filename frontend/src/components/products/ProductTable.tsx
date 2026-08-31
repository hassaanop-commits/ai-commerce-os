import Link from "next/link";
import { productAssetsApi } from "@/lib/products-api";
import type { Product } from "@/types/product";
import { StatusBadge } from "./StatusBadge";
import styles from "./ProductTable.module.css";

function formatPrice(price: string | null, currency: string): string {
  if (price === null) return "—";
  const value = Number(price);
  if (Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
}

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(iso));
}

export function ProductTable({ products, organizationId }: { products: Product[]; organizationId: string }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th></th>
            <th>Product</th>
            <th>SKU</th>
            <th>Price</th>
            <th>Status</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <tr key={product.id}>
              <td className={styles.thumbCell}>
                {product.primary_asset ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={productAssetsApi.fileUrl(organizationId, product.id, product.primary_asset.id)}
                    alt=""
                    className={styles.thumb}
                  />
                ) : (
                  <div className={styles.thumbPlaceholder} aria-hidden="true" />
                )}
              </td>
              <td>
                <Link href={`/dashboard/products/${product.id}`} className={styles.titleLink}>
                  {product.title}
                </Link>
              </td>
              <td className={styles.mono}>{product.sku}</td>
              <td>{formatPrice(product.price, product.currency)}</td>
              <td>
                <StatusBadge status={product.status} />
              </td>
              <td className={styles.muted}>{formatDate(product.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
