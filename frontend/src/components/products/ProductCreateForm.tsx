"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api-client";
import { productsApi } from "@/lib/products-api";
import { useOrganization } from "@/hooks/useOrganization";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import formStyles from "@/components/auth/AuthForm.module.css";
import styles from "./ProductCreateForm.module.css";

interface FormErrors {
  title?: string;
  sku?: string;
  price?: string;
}

export function ProductCreateForm() {
  const router = useRouter();
  const { selectedOrganization } = useOrganization();

  const [title, setTitle] = useState("");
  const [sku, setSku] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function validate(): boolean {
    const nextErrors: FormErrors = {};
    if (!title.trim()) nextErrors.title = "Title is required.";
    if (!sku.trim()) nextErrors.sku = "SKU is required.";
    if (price && Number.isNaN(Number(price))) nextErrors.price = "Enter a valid number.";
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!validate() || !selectedOrganization) return;

    setIsSubmitting(true);
    try {
      const product = await productsApi.create(selectedOrganization.organization_id, {
        title: title.trim(),
        sku: sku.trim(),
        description: description.trim() || undefined,
        price: price ? Number(price) : undefined,
        currency,
      });
      router.push(`/dashboard/products/${product.id}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setFormError("A product with this SKU already exists.");
      } else if (error instanceof ApiError) {
        setFormError(error.detail);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={formStyles.form} onSubmit={handleSubmit} noValidate>
      {formError ? <Alert variant="error">{formError}</Alert> : null}
      <TextField
        label="Title"
        name="title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        error={errors.title}
      />
      <TextField
        label="SKU"
        name="sku"
        value={sku}
        onChange={(e) => setSku(e.target.value)}
        error={errors.sku}
        hint={errors.sku ? undefined : "Must be unique within your workspace."}
      />
      <div className={styles.field}>
        <label htmlFor="description" className={styles.label}>
          Description
        </label>
        <textarea
          id="description"
          name="description"
          className={styles.textarea}
          rows={4}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className={styles.row}>
        <TextField
          label="Price"
          name="price"
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          error={errors.price}
        />
        <div className={styles.field}>
          <label htmlFor="currency" className={styles.label}>
            Currency
          </label>
          <select
            id="currency"
            name="currency"
            className={styles.select}
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
            <option value="CAD">CAD</option>
          </select>
        </div>
      </div>
      <Button type="submit" isLoading={isSubmitting}>
        Create product
      </Button>
    </form>
  );
}
