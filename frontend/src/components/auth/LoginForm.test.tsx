import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "./LoginForm";
import { apiClient, ApiError } from "@/lib/api-client";

const pushMock = vi.fn();
const refreshMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
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

describe("LoginForm", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    pushMock.mockReset();
    refreshMock.mockReset();
  });

  it("requires both fields before submitting", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/enter your password/i)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("redirects to the dashboard on successful login", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "1",
      email: "ada@example.com",
      full_name: "Ada Lovelace",
      status: "active",
      email_verified_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });

    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "a-strong-password-123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(apiClient.post).toHaveBeenCalledWith("/auth/login", {
      email: "ada@example.com",
      password: "a-strong-password-123",
    });
    await vi.waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
    expect(refreshMock).toHaveBeenCalled();
  });

  it("shows a generic invalid-credentials message on a 401 response", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError(401, "Invalid email or password."));

    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong-password-123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
