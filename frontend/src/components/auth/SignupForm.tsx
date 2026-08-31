"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api-client";
import {
  validateConfirmPassword,
  validateEmail,
  validateFullName,
  validatePassword,
} from "@/lib/validation";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import type { User } from "@/types/auth";
import formStyles from "./AuthForm.module.css";

interface FormErrors {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

export function SignupForm() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [signedUpUser, setSignedUpUser] = useState<User | null>(null);

  function validate(): boolean {
    const nextErrors: FormErrors = {
      fullName: validateFullName(fullName) ?? undefined,
      email: validateEmail(email) ?? undefined,
      password: validatePassword(password) ?? undefined,
      confirmPassword: validateConfirmPassword(password, confirmPassword) ?? undefined,
    };
    setErrors(nextErrors);
    return !Object.values(nextErrors).some(Boolean);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const user = await apiClient.post<User>("/auth/signup", {
        full_name: fullName,
        email,
        password,
      });
      setSignedUpUser(user);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setFormError("An account with this email already exists. Try signing in instead.");
      } else if (error instanceof ApiError) {
        setFormError(error.detail);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (signedUpUser) {
    return (
      <Alert variant="success">
        <strong>Check your inbox.</strong> We&apos;ve sent a verification link to{" "}
        {signedUpUser.email}. You&apos;re already signed in, so you can head to your{" "}
        <Link href="/dashboard">dashboard</Link> now and verify whenever you&apos;re ready.
      </Alert>
    );
  }

  return (
    <form className={formStyles.form} onSubmit={handleSubmit} noValidate>
      {formError ? <Alert variant="error">{formError}</Alert> : null}
      <TextField
        label="Full name"
        name="fullName"
        autoComplete="name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        error={errors.fullName}
      />
      <TextField
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={errors.email}
      />
      <TextField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={errors.password}
        hint={errors.password ? undefined : "At least 12 characters."}
      />
      <TextField
        label="Confirm password"
        name="confirmPassword"
        type="password"
        autoComplete="new-password"
        value={confirmPassword}
        onChange={(e) => setConfirmPassword(e.target.value)}
        error={errors.confirmPassword}
      />
      <Button type="submit" isLoading={isSubmitting}>
        Create account
      </Button>
      <p className={formStyles.links}>
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </form>
  );
}
