"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api-client";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import type { Organization } from "@/types/organization";
import formStyles from "@/components/auth/AuthForm.module.css";

export function CreateOrganizationForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!name.trim()) {
      setError("Give your workspace a name.");
      return;
    }
    setError(undefined);

    setIsSubmitting(true);
    try {
      await apiClient.post<Organization>("/organizations", { name });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={formStyles.form} onSubmit={handleSubmit} noValidate>
      {formError ? <Alert variant="error">{formError}</Alert> : null}
      <TextField
        label="Workspace name"
        name="name"
        autoComplete="organization"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error}
        hint={error ? undefined : "You can invite teammates and rename this later."}
      />
      <Button type="submit" isLoading={isSubmitting}>
        Create workspace
      </Button>
    </form>
  );
}
