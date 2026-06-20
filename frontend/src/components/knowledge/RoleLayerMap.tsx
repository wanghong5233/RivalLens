import { Layers3, Radar, Sparkles } from "lucide-react";

import type { CompetitorRoleGroup } from "@/lib/competitorRoles";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface RoleLayerMapProps {
  groups: CompetitorRoleGroup[];
  showActions?: boolean;
  onFocusCompetitor?: (competitorId: string) => void;
  onFocusRole?: (role: string, competitors: string[]) => void;
  onAddWatchlist?: (competitorId: string, sourceRole: string) => void;
}

export function RoleLayerMap({
  groups,
  showActions = false,
  onFocusCompetitor,
  onFocusRole,
  onAddWatchlist,
}: RoleLayerMapProps): JSX.Element | null {
  if (groups.length === 0) {
    return null;
  }
  return (
    <section className="rounded-lg border border-primary/25 bg-primary/[0.05] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="inline-flex items-center gap-2 text-sm font-semibold text-foreground">
            <Layers3 className="h-4 w-4 text-primary" />
            赛道角色分层
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            核心层输出结构化画像，外围层保留简介与趋势线索，可继续发起聚焦分析。
          </p>
        </div>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {groups.map((group) => (
          <article
            key={group.role}
            className="rounded-md border border-white/[0.08] bg-background/40 p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge variant={group.isCore ? "success" : "secondary"}>
                  {group.isCore ? "core" : "peripheral"}
                </Badge>
                <h4 className="text-sm font-medium text-foreground">{group.label}</h4>
              </div>
              <Badge variant="outline">{group.competitors.length} 家</Badge>
            </div>
            {showActions && onFocusRole ? (
              <div className="mt-2">
                <Button
                  size="sm"
                  type="button"
                  variant="ghost"
                  onClick={() => onFocusRole(group.role, group.competitors)}
                >
                  <Radar className="h-3.5 w-3.5" />
                  聚焦该分层
                </Button>
              </div>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {group.competitors.map((competitorId) => (
                <span
                  className="inline-flex items-center gap-1 rounded-full border border-white/[0.08] bg-white/[0.03] px-2 py-1 text-xs text-foreground-muted"
                  key={`${group.role}-${competitorId}`}
                >
                  {competitorId}
                  {showActions && onFocusCompetitor ? (
                    <button
                      className="rounded px-1 text-[10px] text-primary hover:bg-primary/10"
                      onClick={() => onFocusCompetitor(competitorId)}
                      type="button"
                    >
                      <Sparkles className="h-3 w-3" />
                    </button>
                  ) : null}
                  {showActions && onAddWatchlist ? (
                    <button
                      className="rounded px-1 text-[10px] text-primary hover:bg-primary/10"
                      onClick={() => onAddWatchlist(competitorId, group.role)}
                      type="button"
                    >
                      +
                    </button>
                  ) : null}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
