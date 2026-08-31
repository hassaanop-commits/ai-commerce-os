import { describe, it, expect } from "vitest";
import { validateConfirmPassword, validateEmail, validateFullName, validatePassword } from "./validation";

describe("validateEmail", () => {
  it("rejects an empty value", () => {
    expect(validateEmail("")).toMatch(/required/i);
  });

  it("rejects a malformed address", () => {
    expect(validateEmail("not-an-email")).toMatch(/valid/i);
  });

  it("accepts a well-formed address", () => {
    expect(validateEmail("user@example.com")).toBeNull();
  });
});

describe("validatePassword", () => {
  it("rejects passwords shorter than 12 characters", () => {
    expect(validatePassword("short")).toMatch(/12 characters/);
  });

  it("accepts a password of 12+ characters", () => {
    expect(validatePassword("a-strong-password-123")).toBeNull();
  });
});

describe("validateFullName", () => {
  it("rejects blank names", () => {
    expect(validateFullName("   ")).toMatch(/required/i);
  });

  it("accepts a real name", () => {
    expect(validateFullName("Ada Lovelace")).toBeNull();
  });
});

describe("validateConfirmPassword", () => {
  it("rejects a mismatch", () => {
    expect(validateConfirmPassword("password-one-123", "password-two-123")).toMatch(/match/i);
  });

  it("accepts a match", () => {
    expect(validateConfirmPassword("same-password-123", "same-password-123")).toBeNull();
  });
});
