"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { validateEmail } from "@/lib/validation";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import formStyles from "./AuthForm.module.css";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextError = validateEmail(email) ?? undefined;
    setEmailError(nextError);
    if (nextError) return;

    setIsSubmitting(true);
    try {
      await apiClient.post("/auth/password/forgot", { email });
    } catch {
      // Intentionally ignored: the backend returns an identical response
      // whether or not the account exists, so there's nothing to branch on,
      // even on failure -- that's what "always show a safe generic success
      // message" means here.
    } finally {
      setIsSubmitting(false);
      setIsSubmitted(true);
    }
  }

  if (isSubmitted) {
    return (
      <Alert variant="success">
        If an account exists for {email}, we&apos;ve sent a link to reset your password. It
        expires in 1 hour. <Link href="/login">Back to sign in</Link>
      </Alert>
    );
  }

  return (
    <form className={formStyles.form} onSubmit={handleSubmit} noValidate>
      <TextField
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={emailError}
      />
      <Button type="submit" isLoading={isSubmitting}>
        Send reset link
      </Button>
      <p className={formStyles.links}>
        <Link href="/login">Back to sign in</Link>
      </p>
    </form>
  );
}
