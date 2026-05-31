import axios from "axios";

// Dev: empty baseURL → Vite proxy forwards /api to backend (vite.config.ts).
// Prod / override: set VITE_API_BASE_URL (e.g. http://localhost:8010).
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? "" : "http://localhost:8010";

const resolvedBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL =
  resolvedBaseUrl !== undefined && resolvedBaseUrl.length > 0
    ? resolvedBaseUrl
    : DEFAULT_API_BASE_URL;

interface ApiErrorPayload {
  error_code?: string;
  message?: string;
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error);
    }
    const payload = error.response?.data as ApiErrorPayload | undefined;
    if (payload?.error_code && payload?.message) {
      return Promise.reject(new Error(`[${payload.error_code}] ${payload.message}`));
    }
    if (payload?.message) {
      return Promise.reject(new Error(payload.message));
    }
    if (error.message) {
      return Promise.reject(new Error(error.message));
    }
    return Promise.reject(new Error("Unknown API error"));
  },
);
