import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "success" | "warning" | "danger";

export interface ToastProps {
  title: string;
  description?: string;
  variant?: ToastVariant;
  className?: string;
}

const VARIANT_CLASS: Record<ToastVariant, string> = {
  default: "border-border bg-card text-card-foreground",
  success: "border-success/40 bg-success/15 text-success-foreground",
  warning: "border-warning/40 bg-warning/15 text-warning-foreground",
  danger: "border-danger/40 bg-danger/15 text-danger-foreground",
};

export function Toast({ title, description, variant = "default", className }: ToastProps): JSX.Element {
  return (
    <div className={cn("rounded-md border p-3 text-sm shadow", VARIANT_CLASS[variant], className)}>
      <p className="font-medium">{title}</p>
      {description ? <p className="mt-1 text-muted-foreground">{description}</p> : null}
    </div>
  );
}
