import { cn } from "@/lib/utils";

export interface ToastProps {
  title: string;
  description?: string;
  className?: string;
}

export function Toast({ title, description, className }: ToastProps): JSX.Element {
  return (
    <div className={cn("rounded-md border border-border bg-card p-3 text-sm shadow", className)}>
      <p className="font-medium">{title}</p>
      {description ? <p className="mt-1 text-muted-foreground">{description}</p> : null}
    </div>
  );
}
