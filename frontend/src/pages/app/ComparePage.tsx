import { useQueries } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { useRunsList } from "@/api/hooks";
import type { ConclusionItemResponse, RunConclusionsResponse } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "text-success",
  medium: "text-warning",
  low: "text-danger",
};

export function ComparePage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const runsQuery = useRunsList({ limit: 50, offset: 0 });
  const [keyword, setKeyword] = useState("");
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const runs = runsQuery.data?.items ?? [];

  useEffect(() => {
    const raw = searchParams.get("run_ids") ?? "";
    const ids = raw.split(",").map((s) => s.trim()).filter(Boolean);
    if (ids.length > 0) setSelectedRunIds(ids.slice(0, 4));
  }, [searchParams]);

  const filteredRuns = useMemo(
    () => runs.filter((r) => r.user_query.toLowerCase().includes(keyword.trim().toLowerCase())),
    [keyword, runs],
  );

  const conclusionsQueries = useQueries({
    queries: selectedRunIds.map((runId) => ({
      queryKey: ["run-conclusions", runId],
      queryFn: async (): Promise<RunConclusionsResponse> => {
        const { data } = await apiClient.get<RunConclusionsResponse>(`/api/runs/${runId}/conclusions`);
        return data;
      },
      enabled: selectedRunIds.length > 0,
    })),
  });

  const matrix = useMemo(() => {
    const sections = new Set<string>();
    const competitors = new Set<string>();
    const cells = new Map<string, ConclusionItemResponse[]>();

    for (const q of conclusionsQueries) {
      if (!q.data) continue;
      for (const c of q.data.items) {
        sections.add(c.section);
        for (const cid of c.competitor_ids) {
          competitors.add(cid);
          const key = `${c.section}__${cid}`;
          const arr = cells.get(key) ?? [];
          arr.push(c);
          cells.set(key, arr);
        }
      }
    }

    return {
      sections: Array.from(sections),
      competitors: Array.from(competitors),
      getCell: (section: string, competitor: string) => cells.get(`${section}__${competitor}`) ?? [],
    };
  }, [conclusionsQueries]);

  function toggleRun(runId: string): void {
    setSelectedRunIds((prev) =>
      prev.includes(runId) ? prev.filter((id) => id !== runId) : prev.length >= 4 ? prev : [...prev, runId],
    );
  }

  const isLoading = conclusionsQueries.some((q) => q.isLoading);

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-h1 text-foreground">对比矩阵</h1>
        <p className="mt-1 text-caption text-foreground-muted">选择 2-4 个分析任务，跨竞品对比结论。</p>
      </header>

      {/* Run selector */}
      <div className="space-y-3 rounded-lg border border-white/[0.06] bg-surface p-4">
        <Input
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索分析任务..."
          value={keyword}
        />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {filteredRuns.slice(0, 9).map((run) => (
            <button
              key={run.run_id}
              type="button"
              onClick={() => toggleRun(run.run_id)}
              className={cn(
                "rounded-md border p-3 text-left text-caption transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                selectedRunIds.includes(run.run_id)
                  ? "border-primary/40 bg-primary/5"
                  : "border-white/[0.06] hover:border-white/[0.12]",
              )}
            >
              <p className="line-clamp-1 font-medium text-foreground">{run.user_query}</p>
              <p className="mt-0.5 text-micro text-foreground-subtle">{run.status}</p>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <p className="text-micro text-foreground-subtle">已选 {selectedRunIds.length}/4</p>
          {selectedRunIds.length > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setSelectedRunIds([])}>
              清空
            </Button>
          )}
        </div>
      </div>

      {/* Matrix */}
      {isLoading && <Skeleton className="h-40 w-full" />}

      {!isLoading && selectedRunIds.length > 0 && matrix.competitors.length === 0 && (
        <p className="text-caption text-foreground-muted">选中的任务暂无结论数据。</p>
      )}

      {!isLoading && matrix.competitors.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
          <table className="w-full min-w-[700px] border-collapse text-micro">
            <thead className="sticky top-0 z-10 bg-raised">
              <tr>
                <th className="border-b border-r border-white/[0.06] px-3 py-2.5 text-left font-medium text-foreground-muted">
                  段落
                </th>
                {matrix.competitors.map((c) => (
                  <th key={c} className="border-b border-r border-white/[0.06] px-3 py-2.5 text-left font-medium text-foreground">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.sections.map((section) => (
                <tr key={section} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="border-r border-white/[0.06] px-3 py-2.5 align-top font-medium text-foreground-muted">
                    {section}
                  </td>
                  {matrix.competitors.map((competitor) => {
                    const items = matrix.getCell(section, competitor);
                    return (
                      <td key={`${section}-${competitor}`} className="border-r border-white/[0.06] px-3 py-2.5 align-top">
                        {items.length === 0 ? (
                          <span className="text-foreground-subtle">—</span>
                        ) : (
                          <div className="space-y-1.5">
                            {items.slice(0, 3).map((item) => (
                              <div key={item.conclusion_id} className="group relative">
                                <p className="line-clamp-2 text-foreground-muted">{item.claim}</p>
                                <span className={cn("text-[10px] font-medium", CONFIDENCE_COLOR[item.confidence] ?? "text-foreground-subtle")}>
                                  {item.confidence}
                                </span>
                                {/* Hover tooltip */}
                                <div className="pointer-events-none absolute bottom-full left-0 z-20 mb-1 hidden w-64 rounded-md border border-white/[0.1] bg-raised p-2 text-micro text-foreground shadow-raised group-hover:block">
                                  {item.claim}
                                </div>
                              </div>
                            ))}
                            {items.length > 3 && (
                              <p className="text-[10px] text-primary">+{items.length - 3} 更多</p>
                            )}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
