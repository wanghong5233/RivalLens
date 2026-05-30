import { NavLink, Outlet } from "react-router-dom";

import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

export function MarketingShell(): JSX.Element {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-page/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <NavLink to="/">
            <Logo size="sm" />
          </NavLink>
          <nav className="flex items-center gap-1 text-caption">
            <NavLink
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-foreground-muted transition-colors hover:text-foreground",
                  isActive && "text-foreground",
                )
              }
              to="/examples"
            >
              案例库
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-foreground-muted transition-colors hover:text-foreground",
                  isActive && "text-foreground",
                )
              }
              to="/pricing"
            >
              定价
            </NavLink>
            <NavLink
              className="ml-2 rounded-md bg-white/[0.06] px-3.5 py-1.5 text-foreground ring-1 ring-inset ring-white/[0.1] transition-colors hover:bg-white/[0.1]"
              to="/app"
            >
              进入工作区
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-6 py-section">
        <Outlet />
      </main>
    </div>
  );
}
