import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md";
}

export function Logo({ className, size = "md" }: LogoProps): JSX.Element {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={cn(size === "sm" ? "h-5 w-5" : "h-7 w-7")}
      >
        <rect width="32" height="32" rx="8" fill="currentColor" className="text-white/[0.06]" />
        <path d="M8 22V10l6 6-6 6z" fill="hsl(200 90% 52%)" />
        <path d="M16 22V10l6 6-6 6z" fill="hsl(200 90% 52%)" opacity="0.5" />
        <circle cx="26" cy="16" r="2" fill="hsl(200 90% 52%)" />
      </svg>
      <span className={cn("font-semibold tracking-tight text-foreground", size === "sm" ? "text-caption" : "text-body")}>
        RivalLens
      </span>
    </div>
  );
}
