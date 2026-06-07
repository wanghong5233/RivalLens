import {
  BarChart3,
  FolderClock,
  FolderKanban,
  Plus,
  Settings2,
  Shapes,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useSkillCandidates } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  icon: typeof FolderKanban;
  label: string;
  end: boolean;
  /**
   * Optional matcher that lights up the item even when the active URL is not
   * a literal prefix of `to`. Used so /app/runs/:id (run detail variants)
   * keep "我的分析" highlighted — without this they look orphaned in the UI.
   */
  matchPath?: (pathname: string) => boolean;
}

const NAV_ITEMS: readonly NavItem[] = [
  {
    to: "/app",
    icon: FolderKanban,
    label: "我的分析",
    end: true,
    // /app/runs/new* belongs to the "新建分析" tab, so we explicitly exclude
    // it; everything else under /app/runs/* (detail/live/plan/trace/evidence)
    // anchors back to "我的分析".
    matchPath: (pathname) =>
      pathname.startsWith("/app/runs/") && !pathname.startsWith("/app/runs/new"),
  },
  { to: "/app/runs/new", icon: Plus, label: "新建分析", end: false },
  { to: "/app/compare", icon: BarChart3, label: "对比矩阵", end: false },
  { to: "/app/watch", icon: FolderClock, label: "竞品追踪", end: false },
  { to: "/app/templates", icon: Shapes, label: "模板库", end: false },
];

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
  const location = useLocation();

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
          {NAV_ITEMS.map((item) => {
            const matchedExternally = item.matchPath?.(location.pathname) ?? false;
            return (
              <NavLink
                key={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-caption font-medium text-foreground-muted transition-colors",
                    "hover:bg-white/[0.04] hover:text-foreground",
                    (isActive || matchedExternally) && "bg-white/[0.06] text-foreground",
                  )
                }
                to={item.to}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </NavLink>
            );
          })}
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
      {/*
        Why flex column + flex-1 on the inner wrapper:
        chat-style pages need a real height edge so their internal
        `flex-1 overflow-y-auto` actually scrolls instead of letting the
        message list push the whole page taller. Other pages can still
        scroll the main column when content exceeds viewport.
      */}
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col px-8 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
