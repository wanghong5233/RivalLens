import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { useRunReport } from "@/api/hooks";
import { Logo } from "@/components/Logo";
import { Skeleton } from "@/components/ui/skeleton";

export function SharedReportPage(): JSX.Element {
  const { runId } = useParams<{ runId: string }>();
  const reportQuery = useRunReport(runId ?? "", { enabled: Boolean(runId) });

  return (
    <section className="space-y-6 py-8">
      <div className="flex items-center justify-between">
        <Logo size="sm" />
        <Link to="/app" className="text-micro text-primary hover:underline">
          进入工作区
        </Link>
      </div>

      {reportQuery.isLoading && <Skeleton className="h-60 w-full" />}

      {reportQuery.isError && (
        <div className="rounded-lg border border-danger/30 bg-danger/5 p-4 text-caption text-danger">
          报告加载失败：{reportQuery.error.message}
        </div>
      )}

      {reportQuery.data && (
        <article className="prose prose-invert max-w-none rounded-lg border border-white/[0.06] bg-surface p-8 text-caption leading-7 prose-headings:text-foreground prose-p:text-foreground-muted prose-strong:text-foreground prose-a:text-primary">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {reportQuery.data.content_markdown}
          </ReactMarkdown>
        </article>
      )}

      <p className="text-center text-micro text-foreground-subtle">
        由 RivalLens AI 竞品雷达生成 · 数据来源为公开信息
      </p>
    </section>
  );
}
