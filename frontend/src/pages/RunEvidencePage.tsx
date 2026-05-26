import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useRunDetail, useRunEvidence } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function RunEvidencePage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  const [searchParams, setSearchParams] = useSearchParams();

  const competitorId = searchParams.get("competitor_id")?.trim() ?? "";
  const sourceType = searchParams.get("source_type")?.trim() ?? "";
  const highlightedEvidenceId = searchParams.get("evidence_id")?.trim() ?? "";

  const detailQuery = useRunDetail(runId);
  const allEvidenceQuery = useRunEvidence(runId, {}, { enabled: Boolean(runId) });
  const filteredEvidenceQuery = useRunEvidence(
    runId,
    {
      competitor_id: competitorId || undefined,
      source_type: sourceType || undefined,
    },
    { enabled: Boolean(runId) },
  );

  const sourceTypeOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of allEvidenceQuery.data ?? []) {
      values.add(item.source_type);
    }
    return Array.from(values).sort();
  }, [allEvidenceQuery.data]);

  const hasHighlightedEvidence = useMemo(() => {
    if (!highlightedEvidenceId) {
      return false;
    }
    return (filteredEvidenceQuery.data ?? []).some(
      (item) => item.evidence_id === highlightedEvidenceId,
    );
  }, [filteredEvidenceQuery.data, highlightedEvidenceId]);

  function patchSearchParams(next: {
    competitorId?: string;
    sourceType?: string;
    highlightedEvidenceId?: string;
  }): void {
    const params = new URLSearchParams(searchParams);
    if (next.competitorId !== undefined) {
      if (next.competitorId) {
        params.set("competitor_id", next.competitorId);
      } else {
        params.delete("competitor_id");
      }
    }
    if (next.sourceType !== undefined) {
      if (next.sourceType) {
        params.set("source_type", next.sourceType);
      } else {
        params.delete("source_type");
      }
    }
    if (next.highlightedEvidenceId !== undefined) {
      if (next.highlightedEvidenceId) {
        params.set("evidence_id", next.highlightedEvidenceId);
      } else {
        params.delete("evidence_id");
      }
    }
    setSearchParams(params, { replace: true });
  }

  function clearFilters(): void {
    setSearchParams(new URLSearchParams(), { replace: true });
  }

  return (
    <section className="space-y-4">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Evidence Console</h1>
            <p className="font-mono text-xs text-muted-foreground">run_id: {runId}</p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-foreground"
              to={`/runs/${runId}`}
            >
              返回 Run 详情
            </Link>
            <Link
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-foreground"
              to={`/runs/${runId}/trace`}
            >
              查看 Trace
            </Link>
          </div>
        </div>
      </header>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">筛选</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">competitor</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2 text-sm"
              onChange={(event) =>
                patchSearchParams({
                  competitorId: event.currentTarget.value,
                  highlightedEvidenceId: "",
                })
              }
              value={competitorId}
            >
              <option value="">全部</option>
              {(detailQuery.data?.competitors ?? []).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">source_type</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2 text-sm"
              onChange={(event) =>
                patchSearchParams({
                  sourceType: event.currentTarget.value,
                  highlightedEvidenceId: "",
                })
              }
              value={sourceType}
            >
              <option value="">全部</option>
              {sourceTypeOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-end">
            <Button onClick={clearFilters} size="sm" variant="outline">
              清空筛选
            </Button>
          </div>
        </CardContent>
      </Card>

      {allEvidenceQuery.isLoading || filteredEvidenceQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : null}

      {allEvidenceQuery.isError || filteredEvidenceQuery.isError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">
            证据读取失败：
            {allEvidenceQuery.error?.message ?? filteredEvidenceQuery.error?.message ?? "unknown error"}
          </CardContent>
        </Card>
      ) : null}

      {highlightedEvidenceId && !hasHighlightedEvidence ? (
        <Card className="border-amber-400/40">
          <CardContent className="pt-6 text-sm text-amber-200">
            当前高亮 evidence ({highlightedEvidenceId}) 不在筛选结果中，请调整筛选条件。
          </CardContent>
        </Card>
      ) : null}

      {!filteredEvidenceQuery.isLoading &&
      !filteredEvidenceQuery.isError &&
      (filteredEvidenceQuery.data ?? []).length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            当前筛选条件下没有 evidence。
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {(filteredEvidenceQuery.data ?? []).map((item) => {
          const isHighlighted = item.evidence_id === highlightedEvidenceId;
          return (
            <Card
              className={cn(
                "border-border",
                isHighlighted && "border-primary bg-primary/5",
              )}
              key={item.evidence_id}
            >
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span className="font-mono text-foreground">{item.evidence_id}</span>
                  <span>
                    {item.source_type} · {formatDateTime(item.collected_at)}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>competitor: {item.competitor_id ?? "-"}</span>
                  {isHighlighted ? <span className="text-primary">当前高亮</span> : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="whitespace-pre-wrap leading-6">{item.sanitized_text}</p>
                {item.source_title ? <p className="text-xs text-muted-foreground">title: {item.source_title}</p> : null}
                {item.source_url ? (
                  <a
                    className="text-xs text-primary underline-offset-4 hover:underline"
                    href={item.source_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    打开原页面
                  </a>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
