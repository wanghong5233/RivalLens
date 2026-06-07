import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md";
}

const ACCENT = "hsl(200 90% 52%)";

export function Logo({ className, size = "md" }: LogoProps): JSX.Element {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        className={cn(size === "sm" ? "h-5 w-5" : "h-7 w-7")}
      >
        <rect width="32" height="32" rx="8" fill="currentColor" className="text-white/[0.06]" />
        {/* Overlapping scopes: two rivals viewed through a comparative lens */}
        <circle
          cx="12"
          cy="16"
          r="6"
          stroke={ACCENT}
          strokeWidth="1.5"
          fill={ACCENT}
          fillOpacity="0.08"
          opacity="0.55"
        />
        <circle
          cx="20"
          cy="16"
          r="6"
          stroke={ACCENT}
          strokeWidth="1.5"
          fill={ACCENT}
          fillOpacity="0.12"
        />
        <line
          x1="8"
          y1="16"
          x2="24"
          y2="16"
          stroke={ACCENT}
          strokeWidth="1"
          strokeOpacity="0.25"
          strokeLinecap="round"
        />
        {/* Central focus — insight where the two scopes overlap */}
        <circle cx="16" cy="16" r="2.5" fill={ACCENT} />
      </svg>
      <span className={cn("font-semibold tracking-tight text-foreground", size === "sm" ? "text-caption" : "text-body")}>
        RivalLens
      </span>
    </div>
  );
}
