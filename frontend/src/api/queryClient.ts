import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { pushToast } from "@/components/ui/toaster";

interface QueryMetaWithToast {
  errorToast?: boolean;
}

function shouldShowErrorToast(meta: unknown): boolean {
  if (meta === null || typeof meta !== "object") {
    return true;
  }
  return (meta as QueryMetaWithToast).errorToast !== false;
}

export function resolveApiErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return "发生未知错误，请稍后重试。";
  }
  const normalized = error.message.trim();
  if (
    normalized === "Network Error" ||
    normalized.includes("ERR_NETWORK") ||
    normalized.includes("ECONNREFUSED")
  ) {
    return "无法连接后端。请启动 Docker Desktop 后在 backend 目录执行 make up，并确认 API 在 http://localhost:8010 可访问。";
  }
  return error.message;
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (!shouldShowErrorToast(query.meta)) {
        return;
      }
      pushToast({
        title: "数据请求失败",
        description: resolveApiErrorMessage(error),
        variant: "danger",
        durationMs: 6000,
      });
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (!shouldShowErrorToast(mutation.meta)) {
        return;
      }
      pushToast({
        title: "操作执行失败",
        description: resolveApiErrorMessage(error),
        variant: "danger",
        durationMs: 6000,
      });
    },
  }),
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
