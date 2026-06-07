import { useMemo } from "react";
import { Link } from "react-router-dom";

import { useRunEvidence } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";

export interface EvidenceDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runId: string;
  evidenceIds: string[];
}

const SOURCE_TYPE_ICON: Record<string, string> = {
  pricing_page: "📄",
  local_note: "📝",
  unknown_source: "📦",
  g2_review: "⭐",
  reddit: "💬",
  hn_thread: "🟧",
};

function getSourceAuthority(metadata: Record<string, unknown> | null): string {
  const value = metadata?.source_authority;
  return typeof value === "string" && value ? value : "unknown";
}

function toAuthorityLabel(value: string): string {
  if (value === "official") {
    return "官方来源";
  }
  if (value === "third_party") {
    return "第三方来源";
  }
  return "来源未知";
}

export function EvidenceDrawer({
  open,
  onOpenChange,
  runId,
  evidenceIds,
}: EvidenceDrawerProps): JSX.Element {
  const shouldFetch = open && Boolean(runId);
  const evidenceQuery = useRunEvidence(
    runId,
    {},
    {
      enabled: shouldFetch,
    },
  );

  const evidenceRows = useMemo(() => {
    if (!evidenceQuery.data) {
      return [];
    }
    const byId = new Map(evidenceQuery.data.map((item) => [item.evidence_id, item]));
    return evidenceIds.map((evidenceId) => byId.get(evidenceId)).filter((item): item is NonNullable<typeof item> => Boolean(item));
  }, [evidenceIds, evidenceQuery.data]);

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Evidence 引用</SheetTitle>
          <SheetDescription>run_id: {runId}</SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-3 overflow-y-auto">
          {evidenceQuery.isLoading ? (
            <>
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </>
          ) : null}

          {evidenceQuery.isError ? (
            <div className="rounded-md border border-red-400/40 bg-red-500/10 p-3 text-sm text-red-200">
              {evidenceQuery.error.message}
            </div>
          ) : null}

          {!evidenceQuery.isLoading && !evidenceQuery.isError && evidenceRows.length === 0 ? (
            <div className="rounded-md border border-border bg-muted/20 p-3 text-sm text-muted-foreground">
              当前引用未找到对应 evidence 记录。
            </div>
          ) : null}

          {evidenceRows.map((item) => {
            const sourceIcon = SOURCE_TYPE_ICON[item.source_type] ?? "📌";
            const sourceAuthority = getSourceAuthority(item.metadata);
            return (
              <article className="space-y-2 rounded-md border border-border bg-card p-3" key={item.evidence_id}>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{sourceIcon}</span>
                  <span>{item.source_type}</span>
                  <span>·</span>
                  <span>{formatDateTime(item.collected_at)}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant={sourceAuthority === "official" ? "success" : "secondary"}>
                    {toAuthorityLabel(sourceAuthority)}
                  </Badge>
                  <Badge variant={item.desensitized ? "success" : "warning"}>
                    {item.desensitized ? "已脱敏" : "未脱敏"}
                  </Badge>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-6">{item.sanitized_text}</p>
                <div className="text-xs text-muted-foreground">
                  <span>competitor: {item.competitor_id ?? "-"}</span>
                </div>
                <Link
                  className="inline-flex rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:border-primary hover:text-foreground"
                  onClick={() => onOpenChange(false)}
                  to={`/app/runs/${runId}/evidence?evidence_id=${encodeURIComponent(item.evidence_id)}`}
                >
                  查看完整证据
                </Link>
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
              </article>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
