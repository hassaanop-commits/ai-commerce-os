import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResetPasswordForm } from "./ResetPasswordForm";
import { apiClient, ApiError } from "@/lib/api-client";

const pushMock = vi.fn();
let searchParams = new URLSearchParams("token=valid-token");

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: vi.fn() }),
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

describe("ResetPasswordForm", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    pushMock.mockReset();
    searchParams = new URLSearchParams("token=valid-token");
  });

  it("shows an error when the token is missing from the URL", () => {
    searchParams = new URLSearchParams();
    render(<ResetPasswordForm />);

    expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
  });

  it("validates password length and confirmation match", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(/^new password$/i), "short");
    await user.type(screen.getByLabelText(/confirm new password/i), "different");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    expect(await screen.findByText(/12 characters/i)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("submits the token and new password on success", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "1",
      email: "ada@example.com",
      full_name: "Ada Lovelace",
      status: "active",
      email_verified_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });

    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(/^new password$/i), "a-new-strong-password-123");
    await user.type(screen.getByLabelText(/confirm new password/i), "a-new-strong-password-123");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    expect(await screen.findByText(/password has been reset/i)).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/auth/password/reset", {
      token: "valid-token",
      new_password: "a-new-strong-password-123",
    });
  });

  it("shows an expired/invalid message on a 400 response", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError(400, "bad token"));

    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(/^new password$/i), "a-new-strong-password-123");
    await user.type(screen.getByLabelText(/confirm new password/i), "a-new-strong-password-123");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    expect(await screen.findByText(/invalid, expired, or has already been used/i)).toBeInTheDocument();
  });
});
