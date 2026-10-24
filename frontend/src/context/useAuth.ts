import { useContext } from "react";
import { AuthContext } from "./AuthContext";

// Kept out of AuthContext.tsx deliberately — see that file's comment on
// AuthContext for why a component file + a hook export in the same module
// breaks Vite's Fast Refresh.
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
