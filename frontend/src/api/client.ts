import axios from "axios";

const DEFAULT_API_BASE_URL = "";

const resolvedBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = resolvedBaseUrl || DEFAULT_API_BASE_URL;

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
