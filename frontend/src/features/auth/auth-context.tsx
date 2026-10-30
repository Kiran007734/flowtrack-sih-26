import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getAccessToken, setAccessToken } from "@/api/client";
import type { User } from "@/types/domain";

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isBusy: boolean;
  isRestoring: boolean;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isRestoring, setIsRestoring] = useState(() => Boolean(getAccessToken()));

  useEffect(() => {
    if (!getAccessToken()) {
      setIsRestoring(false);
      return undefined;
    }
    let active = true;
    api.me()
      .then((authenticatedUser) => {
        if (active) setUser(authenticatedUser);
      })
      .catch(() => {
        // An expired, revoked, or invalid token must not survive a refresh.
        setAccessToken(null);
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setIsRestoring(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setIsBusy(true);
    try {
      const result = await api.login(email, password);
      setAccessToken(result.access_token);
      const authenticatedUser = result.user ?? await api.me();
      setUser(authenticatedUser);
    } catch (error) {
      setAccessToken(null);
      setUser(null);
      throw error;
    } finally {
      setIsBusy(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsBusy(true);
    try {
      await api.logout();
    } catch {
      // Clearing an in-memory credential remains safe even if the network is unavailable.
    } finally {
      setAccessToken(null);
      setUser(null);
      setIsBusy(false);
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isAuthenticated: user !== null,
    isBusy,
    isRestoring,
    login,
    logout,
  }), [user, isBusy, isRestoring, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// This hook shares the provider's value; the file intentionally exports it with the provider.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
