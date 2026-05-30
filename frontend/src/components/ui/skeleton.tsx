import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return <div className={cn("skeleton-shimmer rounded-md bg-white/[0.06]", className)} {...props} />;
}
