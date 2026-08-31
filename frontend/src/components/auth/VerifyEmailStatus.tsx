"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api-client";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";
import type { User } from "@/types/auth";

type Status = "verifying" | "success" | "error";

export function VerifyEmailStatus() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("This verification link is missing its token.");
      return;
    }

    let cancelled = false;
    apiClient
      .post<User>("/auth/email/verify", { token })
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setStatus("error");
        setMessage(
          error instanceof ApiError
            ? "This link is invalid, expired, or has already been used."
            : "Something went wrong. Please try again."
        );
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "verifying") {
    return <Spinner label="Verifying your email..." />;
  }

  if (status === "success") {
    return (
      <Alert variant="success">
        Your email is verified. <Link href="/dashboard">Go to your dashboard</Link>
      </Alert>
    );
  }

  return (
    <Alert variant="error">
      {message} <Link href="/login">Back to sign in</Link>
    </Alert>
  );
}
