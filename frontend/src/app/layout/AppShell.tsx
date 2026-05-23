import { NavLink, Outlet } from "react-router-dom";

import { useSkillCandidates } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function AppShell(): JSX.Element {
  const pendingCandidatesQuery = useSkillCandidates({
    status: "staging",
    limit: 1,
    offset: 0,
  });
  const pendingCount = pendingCandidatesQuery.data?.total ?? 0;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <span className="text-sm font-semibold tracking-wide">RivalLens Console</span>
          <nav className="flex items-center gap-4 text-sm">
            <NavLink
              className={({ isActive }) =>
                cn(
                  "text-muted-foreground transition-colors hover:text-foreground",
                  isActive && "text-foreground",
                )
              }
              to="/"
            >
              任务列表
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground",
                  isActive && "text-foreground",
                )
              }
              to="/skills/staging"
            >
              Skill 审核台
              {pendingCount > 0 ? <Badge variant="secondary">{pendingCount}</Badge> : null}
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
