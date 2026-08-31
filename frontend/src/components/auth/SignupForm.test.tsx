import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SignupForm } from "./SignupForm";
import { apiClient, ApiError } from "@/lib/api-client";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
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

describe("SignupForm", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
  });

  it("shows validation errors when submitted empty", async () => {
    const user = userEvent.setup();
    render(<SignupForm />);

    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/full name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("shows an error when the passwords do not match", async () => {
    const user = userEvent.setup();
    render(<SignupForm />);

    await user.type(screen.getByLabelText(/full name/i), "Ada Lovelace");
    await user.type(screen.getByLabelText(/^email$/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "a-strong-password-123");
    await user.type(screen.getByLabelText(/confirm password/i), "a-different-password-456");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/do not match/i)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("submits and shows the verification prompt on success", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "1",
      email: "ada@example.com",
      full_name: "Ada Lovelace",
      status: "active",
      email_verified_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });

    const user = userEvent.setup();
    render(<SignupForm />);

    await user.type(screen.getByLabelText(/full name/i), "Ada Lovelace");
    await user.type(screen.getByLabelText(/^email$/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "a-strong-password-123");
    await user.type(screen.getByLabelText(/confirm password/i), "a-strong-password-123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/auth/signup", {
      full_name: "Ada Lovelace",
      email: "ada@example.com",
      password: "a-strong-password-123",
    });
  });

  it("shows a duplicate-email message on a 409 response", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError(409, "conflict"));

    const user = userEvent.setup();
    render(<SignupForm />);

    await user.type(screen.getByLabelText(/full name/i), "Ada Lovelace");
    await user.type(screen.getByLabelText(/^email$/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "a-strong-password-123");
    await user.type(screen.getByLabelText(/confirm password/i), "a-strong-password-123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });
});
