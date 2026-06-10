import { useMemo } from "react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { toCitationLinkMarkdown, transformEvidenceMarkdownUrl } from "@/lib/evidenceLinks";
import { cn } from "@/lib/utils";

export interface ReportArticleProps {
  markdown: string;
  onEvidenceClick: (evidenceIds: string[]) => void;
  className?: string;
}

function extractText(children: ReactNode): string {
  if (typeof children === "string") {
    return children;
  }
  if (Array.isArray(children)) {
    return children.map((child) => extractText(child as ReactNode)).join("");
  }
  return "";
}

function toHeadingId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fa5\s-]/g, "")
    .replace(/\s+/g, "-");
}

/**
 * Renders an evidence-grounded report Markdown string as a professional,
 * print-ready document. Typography comes from `@tailwindcss/typography`
 * (themed to our dark palette in tailwind.config); this layer only adds
 * brand-specific section separators, heading anchors, and clickable
 * evidence citations.
 */
export function ReportArticle({ markdown, onEvidenceClick, className }: ReportArticleProps): JSX.Element {
  const citationLinkedMarkdown = useMemo(() => toCitationLinkMarkdown(markdown), [markdown]);

  return (
    <article
      className={cn(
        "report-article prose prose-base max-w-none rounded-xl border border-white/[0.06] bg-surface px-8 py-9",
        "prose-headings:scroll-mt-24 prose-headings:tracking-tight",
        "prose-h1:mb-6 prose-h1:border-b prose-h1:border-white/[0.1] prose-h1:pb-4",
        "prose-h2:mt-10 prose-h2:border-b prose-h2:border-white/[0.06] prose-h2:pb-2",
        "prose-a:font-medium prose-a:no-underline hover:prose-a:underline",
        "prose-li:my-1 prose-table:overflow-hidden prose-th:font-semibold",
        className,
      )}
    >
      <ReactMarkdown
        components={{
          h2: ({ children }) => <h2 id={toHeadingId(extractText(children))}>{children}</h2>,
          h3: ({ children }) => <h3 id={toHeadingId(extractText(children))}>{children}</h3>,
          table: ({ children }: ComponentPropsWithoutRef<"table">) => (
            <div className="not-prose my-6 overflow-hidden rounded-lg border border-white/[0.08] bg-background/30">
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-gradient-to-l from-surface to-transparent" />
                <div className="scrollbar-prominent-x overflow-x-auto pb-3">
                  <table className="min-w-[760px] border-collapse text-sm">{children}</table>
                </div>
              </div>
            </div>
          ),
          a: ({ href, children }: ComponentPropsWithoutRef<"a">) => {
            if (typeof href === "string" && href.startsWith("evidence://")) {
              const evidenceId = href.replace("evidence://", "");
              return (
                <button
                  className="mx-0.5 inline-flex translate-y-[-1px] cursor-pointer items-center rounded bg-primary/10 px-1.5 align-baseline text-[0.72em] font-medium text-primary no-underline ring-1 ring-inset ring-primary/25 transition-colors hover:bg-primary/20"
                  onClick={() => onEvidenceClick([evidenceId])}
                  type="button"
                >
                  {children}
                </button>
              );
            }
            return (
              <a href={href} rel="noreferrer" target="_blank">
                {children}
              </a>
            );
          },
        }}
        remarkPlugins={[remarkGfm]}
        urlTransform={transformEvidenceMarkdownUrl}
      >
        {citationLinkedMarkdown}
      </ReactMarkdown>
    </article>
  );
}
