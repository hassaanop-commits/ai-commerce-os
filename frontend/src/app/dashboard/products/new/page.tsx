"use client";

import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { ProductCreateForm } from "@/components/products/ProductCreateForm";
import styles from "./page.module.css";

export default function NewProductPage() {
  return (
    <div className={styles.page}>
      <Link href="/dashboard/products" className={styles.backLink}>
        ← Back to products
      </Link>
      <Card className={styles.card}>
        <h1>New product</h1>
        <p className={styles.lede}>Add a product to your catalog. You can upload photos after creating it.</p>
        <ProductCreateForm />
      </Card>
    </div>
  );
}
