import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "./useAuth";
import { apiClient } from "@/lib/api-client";

const pushMock = vi.fn();
const refreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: vi.fn() },
}));

const testUser = {
  id: "1",
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  status: "active",
  email_verified_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function Probe() {
  const { user, logout } = useAuth();
  return (
    <div>
      <p>{user.email}</p>
      <button onClick={() => logout()}>Sign out</button>
    </div>
  );
}

describe("useAuth", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset().mockResolvedValue(undefined);
    pushMock.mockReset();
    refreshMock.mockReset();
  });

  it("exposes the authenticated user provided to AuthProvider", () => {
    render(
      <AuthProvider user={testUser}>
        <Probe />
      </AuthProvider>
    );

    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("calls the logout endpoint and redirects to login", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider user={testUser}>
        <Probe />
      </AuthProvider>
    );

    await user.click(screen.getByRole("button", { name: /sign out/i }));

    expect(apiClient.post).toHaveBeenCalledWith("/auth/logout");
    expect(pushMock).toHaveBeenCalledWith("/login");
    expect(refreshMock).toHaveBeenCalled();
  });

  it("throws when used outside of an AuthProvider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/AuthProvider/);
    consoleError.mockRestore();
  });
});
