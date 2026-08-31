"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import type { User } from "@/types/auth";

interface AuthContextValue {
  user: User;
  logout: () => Promise<void>;
  isLoggingOut: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ user, children }: { user: User; children: ReactNode }) {
  const router = useRouter();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const logout = useCallback(async () => {
    setIsLoggingOut(true);
    try {
      await apiClient.post("/auth/logout");
    } finally {
      setIsLoggingOut(false);
      router.push("/login");
      router.refresh();
    }
  }, [router]);

  return <AuthContext.Provider value={{ user, logout, isLoggingOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
