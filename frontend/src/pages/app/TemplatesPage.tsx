import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function TemplatesPage(): JSX.Element {
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-h1 text-foreground">模板库</h1>
        <p className="mt-1 text-caption text-foreground-muted">从预设模板快速启动竞品分析。</p>
      </header>

      <div className="rounded-lg border border-white/[0.06] bg-surface p-8 text-center">
        <p className="text-caption text-foreground-muted">模板库即将上线，敬请期待。</p>
        <Button asChild size="sm" variant="secondary" className="mt-4">
          <Link to="/app/runs/new">直接新建分析</Link>
        </Button>
      </div>
    </section>
  );
}
