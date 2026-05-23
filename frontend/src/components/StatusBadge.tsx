import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type StatusType = "running" | "completed" | "degraded" | "failed" | string;

const STATUS_META: Record<string, { icon: string; label: string; className: string }> = {
  running: {
    icon: "⏳",
    label: "进行中",
    className: "bg-amber-500/15 text-amber-300",
  },
  completed: {
    icon: "✓",
    label: "完成",
    className: "bg-emerald-500/15 text-emerald-300",
  },
  degraded: {
    icon: "⚠",
    label: "降级",
    className: "bg-orange-500/15 text-orange-300",
  },
  failed: {
    icon: "✗",
    label: "失败",
    className: "bg-red-500/15 text-red-300",
  },
};

export interface StatusBadgeProps {
  status: StatusType;
}

export function StatusBadge({ status }: StatusBadgeProps): JSX.Element {
  const meta = STATUS_META[status] ?? {
    icon: "•",
    label: status,
    className: "bg-secondary text-secondary-foreground",
  };
  return (
    <Badge className={cn("border-transparent px-2 py-0.5 font-medium", meta.className)} variant="secondary">
      <span className="mr-1">{meta.icon}</span>
      {meta.label}
    </Badge>
  );
}
