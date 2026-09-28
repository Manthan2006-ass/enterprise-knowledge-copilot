import React, { createContext, useContext, useState, useCallback } from "react";
import { api } from "../api.js";

const AuthContext = createContext(null);

const TOKEN_KEY = "ec_access_token";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [userId, setUserId] = useState(null);
  const [checking, setChecking] = useState(true);

  const applyToken = useCallback(async (newToken) => {
    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    const me = await api.me(newToken);
    setUserId(me.user_id);
  }, []);

  const login = useCallback(
    async (email, password) => {
      const { access_token } = await api.login(email, password);
      await applyToken(access_token);
    },
    [applyToken]
  );

  const signup = useCallback(async (email, password) => {
    await api.signup(email, password);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUserId(null);
  }, []);

  // On first load, validate any stored token
  React.useEffect(() => {
    (async () => {
      if (token) {
        try {
          const me = await api.me(token);
          setUserId(me.user_id);
        } catch {
          logout();
        }
      }
      setChecking(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, userId, checking, login, signup, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
