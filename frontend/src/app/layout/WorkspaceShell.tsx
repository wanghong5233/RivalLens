import {
  BarChart3,
  FolderClock,
  LayoutDashboard,
  Plus,
  Settings2,
  Shapes,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useSkillCandidates } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/app", icon: LayoutDashboard, label: "仪表盘", end: true },
  { to: "/app/runs/new", icon: Plus, label: "新建分析", end: false },
  { to: "/app/compare", icon: BarChart3, label: "对比矩阵", end: false },
  { to: "/app/watch", icon: FolderClock, label: "竞品追踪", end: false },
  { to: "/app/templates", icon: Shapes, label: "模板库", end: false },
] as const;

export function WorkspaceShell(): JSX.Element {
  const pendingCandidatesQuery = useSkillCandidates(
    {
      status: "staging",
      limit: 1,
      offset: 0,
    },
    { errorToast: false },
  );
  const pendingCount = pendingCandidatesQuery.data?.total ?? 0;

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/[0.06] bg-page">
        {/* Brand */}
        <div className="flex h-14 items-center px-4">
          <NavLink to="/app">
            <Logo size="sm" />
          </NavLink>
        </div>

        {/* Main nav */}
        <nav className="flex-1 space-y-0.5 px-2 py-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-caption font-medium text-foreground-muted transition-colors",
                  "hover:bg-white/[0.04] hover:text-foreground",
                  isActive && "bg-white/[0.06] text-foreground",
                )
              }
              to={item.to}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Bottom section */}
        <div className="border-t border-white/[0.04] p-2">
          <NavLink
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-caption font-medium text-foreground-muted transition-colors",
                "hover:bg-white/[0.04] hover:text-foreground",
                isActive && "bg-white/[0.06] text-foreground",
              )
            }
            to="/app/settings/skill-admin"
          >
            <Settings2 className="h-4 w-4 shrink-0" />
            设置
            {pendingCount > 0 && (
              <Badge variant="default" className="ml-auto">
                {pendingCount}
              </Badge>
            )}
          </NavLink>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
