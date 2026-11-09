"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ApiError,
  AUTH_EXPIRED_EVENT,
  fetchCurrentUser,
  loginUser,
  logoutUser,
  messageFromError,
  registerUser,
  type LoginInput,
  type RegisterInput,
  type UserProfile,
} from "@/lib/api";

type AuthContextValue = {
  user: UserProfile | null;
  loading: boolean;
  error: string | null;
  login: (input: LoginInput) => Promise<UserProfile>;
  register: (input: RegisterInput) => Promise<UserProfile>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);

    try {
      const profile = await fetchCurrentUser(signal);
      setUser(profile);
    } catch (cause) {
      if (signal?.aborted) {
        return;
      }
      if (cause instanceof ApiError && cause.status === 401) {
        setUser(null);
      } else {
        setUser(null);
        setError(
          "Unable to reach the Ideon backend. Check that the API is running, then retry.",
        );
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadSession(controller.signal);
    return () => controller.abort();
  }, [loadSession]);

  useEffect(() => {
    function handleExpiredSession() {
      setUser(null);
      setError(null);
    }

    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpiredSession);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpiredSession);
    };
  }, []);

  const refresh = useCallback(async () => {
    await loadSession();
  }, [loadSession]);

  const login = useCallback(async (input: LoginInput) => {
    setError(null);
    const profile = await loginUser(input);
    setUser(profile);
    return profile;
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    setError(null);
    const profile = await registerUser(input);
    setUser(profile);
    return profile;
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch (cause) {
      // Local state must still clear even if the network fails.
      setError(messageFromError(cause));
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, error, login, register, logout, refresh }),
    [user, loading, error, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return context;
}
