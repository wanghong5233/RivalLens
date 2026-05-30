import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { pushToast } from "@/components/ui/toaster";

function resolveErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "发生未知错误，请稍后重试。";
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      pushToast({
        title: "数据请求失败",
        description: resolveErrorMessage(error),
        variant: "danger",
      });
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      pushToast({
        title: "操作执行失败",
        description: resolveErrorMessage(error),
        variant: "danger",
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
