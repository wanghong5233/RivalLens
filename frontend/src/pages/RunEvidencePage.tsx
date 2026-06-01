import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Filter, FileText, ExternalLink, AlertCircle } from "lucide-react";

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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-sm border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to={`/runs/${runId}`} className="flex items-center gap-2 text-slate-600 hover:text-slate-900">
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回分析详情</span>
              </Link>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h1 className="text-lg font-semibold text-slate-900">证据控制台</h1>
                <p className="text-xs text-slate-500 font-mono">{runId}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
                to={`/runs/${runId}/trace`}
              >
                <FileText className="h-4 w-4" />
                查看 Trace
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Filter Card */}
        <Card className="border-0 shadow-md mb-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
              <Filter className="h-5 w-5" />
              筛选条件
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">竞品</label>
              <select
                className="h-11 w-full rounded-xl border border-slate-200 bg-white px-4 text-slate-800 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
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
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">来源类型</label>
              <select
                className="h-11 w-full rounded-xl border border-slate-200 bg-white px-4 text-slate-800 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
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
            </div>

            <div className="sm:col-span-2 flex items-end">
              <Button 
                onClick={clearFilters} 
                size="sm" 
                variant="outline"
                className="border-slate-300 text-slate-700 hover:bg-slate-50"
              >
                清空筛选
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {allEvidenceQuery.isLoading || filteredEvidenceQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-32 w-full rounded-xl" />
            <Skeleton className="h-32 w-full rounded-xl" />
          </div>
        ) : null}

        {/* Error State */}
        {allEvidenceQuery.isError || filteredEvidenceQuery.isError ? (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-6 w-6 text-amber-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">证据读取失败</p>
                  <p className="text-xs text-amber-600 mt-1">
                    {allEvidenceQuery.error?.message ?? filteredEvidenceQuery.error?.message ?? "unknown error"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Highlighted Evidence Not Found */}
        {highlightedEvidenceId && !hasHighlightedEvidence ? (
          <Card className="border-0 shadow-md bg-amber-50 mb-6">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-amber-700">
                  当前高亮 evidence ({highlightedEvidenceId}) 不在筛选结果中，请调整筛选条件。
                </p>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Empty State */}
        {!filteredEvidenceQuery.isLoading &&
        !filteredEvidenceQuery.isError &&
        (filteredEvidenceQuery.data ?? []).length === 0 ? (
          <Card className="border-0 shadow-md bg-slate-50/50">
            <CardContent className="pt-16 pb-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center">
                <FileText className="h-8 w-8 text-slate-400" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">暂无证据</h3>
              <p className="text-slate-500 text-sm">当前筛选条件下没有找到证据数据。</p>
            </CardContent>
          </Card>
        ) : null}

        {/* Evidence List */}
        <div className="space-y-4">
          {(filteredEvidenceQuery.data ?? []).map((item) => {
            const isHighlighted = item.evidence_id === highlightedEvidenceId;
            return (
              <Card
                className={cn(
                  "border-0 shadow-md transition-all",
                  isHighlighted && "border-2 border-blue-500 bg-blue-50",
                )}
                key={item.evidence_id}
              >
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono text-sm text-slate-900">{item.evidence_id}</span>
                      {isHighlighted && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                          当前高亮
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-500">
                      {item.source_type} · {formatDateTime(item.collected_at)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-slate-500">
                    <span>竞品: {item.competitor_id ?? "-"}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-sm text-slate-700 whitespace-pre-wrap leading-6">{item.sanitized_text}</p>
                  </div>
                  {item.source_title && (
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <ExternalLink className="h-3 w-3" />
                      <span>标题: {item.source_title}</span>
                    </div>
                  )}
                  {item.source_url && (
                    <a
                      className="inline-flex items-center gap-2 text-xs text-blue-600 hover:text-blue-700 transition-all"
                      href={item.source_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      <ExternalLink className="h-3 w-3" />
                      打开原页面
                    </a>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white border-t border-slate-100 mt-auto">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-sm text-slate-500">
            RivalLens - AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}
