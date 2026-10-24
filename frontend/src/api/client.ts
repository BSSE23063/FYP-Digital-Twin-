import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export const apiClient = axios.create({ baseURL: API_BASE });

export function setAuthToken(token: string | null) {
  if (token) {
    apiClient.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common["Authorization"];
  }
}

/** Pulls FastAPI's {"detail": "..."} out of an error response, falling back
 * to the raw axios message so a failed call never shows "[object Object]". */
export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (err.code === "ERR_NETWORK") return `Can't reach the backend at ${API_BASE} — is it running?`;
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
