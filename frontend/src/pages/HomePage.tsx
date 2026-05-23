import { useNavigate } from "react-router-dom";

import { useRunsList } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

export function HomePage(): JSX.Element {
  const navigate = useNavigate();
  const runsQuery = useRunsList({ limit: 20, offset: 0 });

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">任务列表</h1>
          <p className="text-sm text-muted-foreground">查看历史 run，并可快速进入报告与 Trace。</p>
        </div>
        <Button onClick={() => navigate("/runs/new")}>+ 新建分析</Button>
      </div>

      {runsQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : null}

      {runsQuery.isError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">{runsQuery.error.message}</CardContent>
        </Card>
      ) : null}

      {!runsQuery.isLoading && !runsQuery.isError && runsQuery.data?.items.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            暂无 run，点击右上角“新建分析”开始第一条任务。
          </CardContent>
        </Card>
      ) : null}

      {!runsQuery.isLoading && !runsQuery.isError ? (
        <div className="space-y-3">
          {runsQuery.data?.items.map((run) => (
            <Card
              className="cursor-pointer transition-colors hover:border-primary/60"
              key={run.run_id}
              onClick={() => navigate(`/runs/${run.run_id}`)}
              role="button"
            >
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-4">
                  <CardTitle className="text-base">{run.user_query}</CardTitle>
                  <StatusBadge status={run.status} />
                </div>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-muted-foreground">
                <p className="font-mono text-xs text-foreground">{run.run_id}</p>
                <p>
                  pack: {run.industry_pack} · steps {run.step_count} · evidence {run.evidence_count}
                </p>
                <p>
                  started: {formatDateTime(run.started_at)} ({formatRelativeTime(run.started_at)})
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </section>
  );
}
