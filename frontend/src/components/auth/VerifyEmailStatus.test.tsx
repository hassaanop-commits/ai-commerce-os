import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { VerifyEmailStatus } from "./VerifyEmailStatus";
import { apiClient, ApiError } from "@/lib/api-client";

let searchParams = new URLSearchParams("token=valid-token");

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: vi.fn() },
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.status = status;
      this.detail = detail;
    }
  },
}));

describe("VerifyEmailStatus", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    searchParams = new URLSearchParams("token=valid-token");
  });

  it("shows success once verification resolves", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "1",
      email: "ada@example.com",
      full_name: "Ada Lovelace",
      status: "active",
      email_verified_at: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    });

    render(<VerifyEmailStatus />);

    expect(await screen.findByText(/email is verified/i)).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/auth/email/verify", { token: "valid-token" });
  });

  it("shows an error message when the token is invalid or expired", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError(400, "bad token"));

    render(<VerifyEmailStatus />);

    expect(await screen.findByText(/invalid, expired, or has already been used/i)).toBeInTheDocument();
  });

  it("shows an error when the URL has no token at all", async () => {
    searchParams = new URLSearchParams();

    render(<VerifyEmailStatus />);

    expect(await screen.findByText(/missing its token/i)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
