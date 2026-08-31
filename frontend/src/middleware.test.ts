import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "./middleware";

function makeRequest(path: string, cookies: Record<string, string> = {}) {
  const request = new NextRequest(new URL(path, "http://localhost:3000"));
  for (const [name, value] of Object.entries(cookies)) {
    request.cookies.set(name, value);
  }
  return request;
}

describe("middleware", () => {
  it("redirects unauthenticated requests away from /dashboard to /login", () => {
    const response = middleware(makeRequest("/dashboard"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("/login");
  });

  it("redirects unauthenticated requests away from nested /organizations routes", () => {
    const response = middleware(makeRequest("/organizations/new"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("/login");
  });

  it("allows an authenticated request through to /dashboard", () => {
    const response = middleware(makeRequest("/dashboard", { session_token: "abc" }));

    expect(response.headers.get("location")).toBeNull();
  });

  it("redirects an authenticated user away from /login", () => {
    const response = middleware(makeRequest("/login", { session_token: "abc" }));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("/dashboard");
  });

  it("allows an unauthenticated request through to /login", () => {
    const response = middleware(makeRequest("/login"));

    expect(response.headers.get("location")).toBeNull();
  });
});
