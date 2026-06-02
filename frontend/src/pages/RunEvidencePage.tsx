import type { LucideIcon } from "lucide-react";
import { CircleDollarSign, FileText, Globe, MessageSquareText, Sparkles } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useRunDetail, useRunEvidence } from "@/api/hooks";
import type { EvidenceListItemResponse } from "@/api/types";
import { RunBreadcrumb } from "@/components/RunBreadcrumb";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatRunTitle } from "@/lib/format";
import { cn } from "@/lib/utils";

interface SourceMeta {
  label: string;
  icon: LucideIcon;
}

function toSourceMeta(sourceType: string): SourceMeta {
  const normalized = sourceType.toLowerCase();
  if (normalized.includes("pricing")) {
    return { label: "定价页", icon: CircleDollarSign };
  }
  if (normalized.includes("review")) {
    return { label: "用户评论", icon: MessageSquareText };
  }
  if (normalized.includes("snapshot")) {
    return { label: "网页快照", icon: FileText };
  }
  if (normalized.includes("article")) {
    return { label: "文章信息", icon: FileText };
  }
  return { label: sourceType, icon: Globe };
}

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
  const groupedEvidence = useMemo(() => {
    const groups = new Map<string, EvidenceListItemResponse[]>();
    for (const item of filteredEvidenceQuery.data ?? []) {
      const groupKey = item.competitor_id ?? "未标注竞品";
      const current = groups.get(groupKey) ?? [];
      current.push(item);
      groups.set(groupKey, current);
    }
    return Array.from(groups.entries()).sort(([left], [right]) =>
      left.localeCompare(right, "zh-CN"),
    );
  }, [filteredEvidenceQuery.data]);

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
    <section className="space-y-5">
      <header className="space-y-3">
        <RunBreadcrumb run={detailQuery.data} current="证据库" />
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="inline-flex items-center gap-2 text-xs text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              可追溯证据库
            </p>
            <h1
              className="truncate text-2xl font-semibold"
              title={detailQuery.data?.user_query}
            >
              {detailQuery.data ? formatRunTitle(detailQuery.data, { max: 60 }) : "证据库"}
            </h1>
            <p className="text-xs text-muted-foreground">run_id: {runId}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Link
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-foreground"
              to={`/app/runs/${runId}/trace`}
            >
              查看 Trace
            </Link>
          </div>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">当前筛选结果</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {(filteredEvidenceQuery.data ?? []).length}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">总证据量</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{(allEvidenceQuery.data ?? []).length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">已分组竞品</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{groupedEvidence.length}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">筛选</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">competitor</span>
            <NativeSelect
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
            </NativeSelect>
          </label>

          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">source_type</span>
            <NativeSelect
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
            </NativeSelect>
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

      <div className="space-y-4">
        {groupedEvidence.map(([groupKey, evidenceItems]) => (
          <Card key={groupKey}>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">{groupKey}</CardTitle>
                <Badge variant="secondary">{evidenceItems.length} 条证据</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {evidenceItems.map((item) => {
                const sourceMeta = toSourceMeta(item.source_type);
                const SourceIcon = sourceMeta.icon;
                const isHighlighted = item.evidence_id === highlightedEvidenceId;
                return (
                  <article
                    className={cn(
                      "space-y-3 rounded-lg border border-border/90 bg-background/70 p-4",
                      isHighlighted && "border-primary bg-primary/10",
                    )}
                    key={item.evidence_id}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                        <SourceIcon className="h-3.5 w-3.5 text-primary" />
                        <span>{sourceMeta.label}</span>
                        <span>·</span>
                        <span>{formatDateTime(item.collected_at)}</span>
                      </div>
                      <span className="font-mono text-xs text-muted-foreground">{item.evidence_id}</span>
                    </div>
                    {item.source_title ? <p className="text-sm font-medium text-foreground">{item.source_title}</p> : null}
                    <p className="whitespace-pre-wrap text-sm leading-6 text-slate-200">{item.sanitized_text}</p>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                      {isHighlighted ? <span className="rounded bg-primary/20 px-2 py-0.5 text-primary">报告高亮引用</span> : null}
                      {item.source_url ? (
                        <a
                          className="text-primary underline-offset-4 hover:underline"
                          href={item.source_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          打开原页面
                        </a>
                      ) : (
                        <span>无原始链接</span>
                      )}
                    </div>
                  </article>
                );
              })}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
