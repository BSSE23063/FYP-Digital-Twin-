import { createContext, useEffect, useState, type ReactNode } from "react";
import { setAuthToken } from "../api/client";
import { loginOwner, loginVisitor, registerOwner } from "../api/endpoints";

export type Role = "owner" | "visitor";

interface AuthState {
  role: Role;
  token: string | null;
  userId: string | null;
  email: string | null;
  displayName: string | null;
}

export interface AuthContextValue extends AuthState {
  isAuthenticated: boolean;
  setRole: (role: Role) => void;
  doLoginOwner: (email: string, password: string) => Promise<void>;
  doRegisterOwner: (email: string, password: string, displayName: string) => Promise<void>;
  doLoginVisitor: (email: string, displayName: string) => Promise<void>;
  logout: () => void;
}

const STORAGE_KEY = "t2rag_auth";

const EMPTY_STATE: AuthState = { role: "visitor", token: null, userId: null, email: null, displayName: null };

function loadState(): AuthState {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return { ...EMPTY_STATE, ...JSON.parse(saved) };
  } catch {
    // ignore corrupt/blocked storage — fall through to default
  }
  return EMPTY_STATE;
}

// Exported so useAuth.ts (a separate file — see its own comment for why) can
// read from the same Context object. Vite's react-refresh plugin can only
// Fast-Refresh a module that exports ONLY components; a file exporting both
// a component (AuthProvider) and a plain hook function (useAuth) is a known
// incompatibility that silently breaks HMR (confirmed: this exact file threw
// repeated "Could not Fast Refresh" invalidations this session, which left
// the browser with a stale/duplicated Context and produced a very confusing
// "useAuth must be used within AuthProvider" error despite completely
// correct provider nesting in App.tsx — cost real debugging time before the
// cause was found). Splitting the hook into its own file is the fix.
export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadState);

  useEffect(() => {
    setAuthToken(state.token);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // private browsing / storage disabled — the session still works, it just
      // won't survive a reload
    }
  }, [state]);

  const setRole = (role: Role) => setState((s) => ({ ...EMPTY_STATE, role }));

  const doLoginOwner = async (email: string, password: string) => {
    const data = await loginOwner(email, password);
    setState({ role: "owner", token: data.token, userId: data.user_id, email: data.email, displayName: data.display_name });
  };

  const doRegisterOwner = async (email: string, password: string, displayName: string) => {
    const data = await registerOwner(email, password, displayName);
    setState({ role: "owner", token: data.token, userId: data.user_id, email: data.email, displayName: data.display_name });
  };

  const doLoginVisitor = async (email: string, displayName: string) => {
    const data = await loginVisitor(email, displayName);
    setState({ role: "visitor", token: data.token, userId: data.user_id, email: data.email, displayName: data.display_name });
  };

  const logout = () => setState((s) => ({ ...EMPTY_STATE, role: s.role }));

  return (
    <AuthContext.Provider
      value={{
        ...state,
        isAuthenticated: Boolean(state.token),
        setRole,
        doLoginOwner,
        doRegisterOwner,
        doLoginVisitor,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
