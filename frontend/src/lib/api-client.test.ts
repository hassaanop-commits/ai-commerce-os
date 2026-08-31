import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient, ApiError } from "./api-client";

describe("apiClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("returns parsed JSON on a successful GET", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );

    const result = await apiClient.get<{ id: string }>("/auth/me");

    expect(result).toEqual({ id: "1" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/auth/me",
      expect.objectContaining({ method: "GET", credentials: "same-origin" })
    );
  });

  it("returns undefined for a 204 response", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    const result = await apiClient.post("/auth/logout");

    expect(result).toBeUndefined();
  });

  it("throws an ApiError carrying the backend's status and detail on failure", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid email or password." }), {
        status: 401,
        headers: { "content-type": "application/json" },
      })
    );

    const promise = apiClient.post("/auth/login", { email: "a@b.com", password: "x" });
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({
      status: 401,
      detail: "Invalid email or password.",
    });
  });

  it("attaches the CSRF header from the csrf_token cookie on mutating requests", async () => {
    document.cookie = "csrf_token=abc123";
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    await apiClient.post("/organizations", { name: "Acme" });

    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBe("abc123");
  });

  it("does not attach a CSRF header on GET requests", async () => {
    document.cookie = "csrf_token=abc123";
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } })
    );

    await apiClient.get("/organizations");

    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBeNull();
  });
});
