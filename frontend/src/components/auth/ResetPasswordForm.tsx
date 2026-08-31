"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api-client";
import { validateConfirmPassword, validatePassword } from "@/lib/validation";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import type { User } from "@/types/auth";
import formStyles from "./AuthForm.module.css";

export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | undefined>();
  const [confirmError, setConfirmError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDone, setIsDone] = useState(false);

  if (!token) {
    return (
      <Alert variant="error">
        This password reset link is missing its token. Request a new one from{" "}
        <Link href="/forgot-password">the forgot password page</Link>.
      </Alert>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const nextPasswordError = validatePassword(password) ?? undefined;
    const nextConfirmError = validateConfirmPassword(password, confirmPassword) ?? undefined;
    setPasswordError(nextPasswordError);
    setConfirmError(nextConfirmError);
    if (nextPasswordError || nextConfirmError) return;

    setIsSubmitting(true);
    try {
      await apiClient.post<User>("/auth/password/reset", { token, new_password: password });
      setIsDone(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        setFormError("This reset link is invalid, expired, or has already been used.");
      } else if (error instanceof ApiError) {
        setFormError(error.detail);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isDone) {
    return <Alert variant="success">Your password has been reset. Redirecting you to sign in...</Alert>;
  }

  return (
    <form className={formStyles.form} onSubmit={handleSubmit} noValidate>
      {formError ? (
        <Alert variant="error">
          {formError} <Link href="/forgot-password">Request a new link</Link>
        </Alert>
      ) : null}
      <TextField
        label="New password"
        name="password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={passwordError}
        hint={passwordError ? undefined : "At least 12 characters."}
      />
      <TextField
        label="Confirm new password"
        name="confirmPassword"
        type="password"
        autoComplete="new-password"
        value={confirmPassword}
        onChange={(e) => setConfirmPassword(e.target.value)}
        error={confirmError}
      />
      <Button type="submit" isLoading={isSubmitting}>
        Reset password
      </Button>
    </form>
  );
}
