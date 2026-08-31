"use client";

import { useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api-client";
import { productsApi } from "@/lib/products-api";
import type { Product, ProductStatus } from "@/types/product";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import formStyles from "@/components/auth/AuthForm.module.css";
import createFormStyles from "./ProductCreateForm.module.css";

export function ProductOverview({
  organizationId,
  product,
  onSaved,
}: {
  organizationId: string;
  product: Product;
  onSaved: (product: Product) => void;
}) {
  const [title, setTitle] = useState(product.title);
  const [sku, setSku] = useState(product.sku);
  const [description, setDescription] = useState(product.description ?? "");
  const [price, setPrice] = useState(product.price ?? "");
  const [currency, setCurrency] = useState(product.currency);
  const [status, setStatus] = useState<ProductStatus>(product.status);
  const [errors, setErrors] = useState<{ title?: string; sku?: string; price?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  function validate(): boolean {
    const next: typeof errors = {};
    if (!title.trim()) next.title = "Title is required.";
    if (!sku.trim()) next.sku = "SKU is required.";
    if (price && Number.isNaN(Number(price))) next.price = "Enter a valid number.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSuccessMessage(null);
    if (!validate()) return;

    setIsSaving(true);
    try {
      const updated = await productsApi.update(organizationId, product.id, {
        title: title.trim(),
        sku: sku.trim(),
        description: description.trim() || null,
        price: price === "" ? null : Number(price),
        currency,
        status,
      });
      onSaved(updated);
      setSuccessMessage("Changes saved.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setFormError("A product with this SKU already exists.");
      } else if (error instanceof ApiError) {
        setFormError(error.detail);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className={formStyles.form} onSubmit={handleSubmit} noValidate>
      {formError ? <Alert variant="error">{formError}</Alert> : null}
      {successMessage ? <Alert variant="success">{successMessage}</Alert> : null}
      <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
      <TextField label="SKU" value={sku} onChange={(e) => setSku(e.target.value)} error={errors.sku} />
      <div className={createFormStyles.field}>
        <label htmlFor="overview-description" className={createFormStyles.label}>
          Description
        </label>
        <textarea
          id="overview-description"
          className={createFormStyles.textarea}
          rows={4}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className={createFormStyles.row}>
        <TextField
          label="Price"
          inputMode="decimal"
          value={String(price)}
          onChange={(e) => setPrice(e.target.value)}
          error={errors.price}
        />
        <div className={createFormStyles.field}>
          <label htmlFor="overview-currency" className={createFormStyles.label}>
            Currency
          </label>
          <select
            id="overview-currency"
            className={createFormStyles.select}
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
      <div className={createFormStyles.field}>
        <label htmlFor="overview-status" className={createFormStyles.label}>
          Status
        </label>
        <select
          id="overview-status"
          className={createFormStyles.select}
          value={status}
          onChange={(e) => setStatus(e.target.value as ProductStatus)}
        >
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </div>
      <Button type="submit" isLoading={isSaving}>
        Save changes
      </Button>
    </form>
  );
}
