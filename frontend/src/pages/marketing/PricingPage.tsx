import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const PLANS = [
  {
    name: "Starter",
    price: "免费",
    features: ["每月 5 次分析", "基础 Battlecard", "Markdown 导出", "公开分享链接"],
    cta: "当前方案",
    active: true,
  },
  {
    name: "Pro",
    price: "即将上线",
    features: ["无限分析", "高级对比矩阵", "PDF 导出", "Watchlist 自动刷新", "优先队列"],
    cta: "即将上线",
    active: false,
  },
  {
    name: "Team",
    price: "即将上线",
    features: ["Pro 全部功能", "团队协作", "自定义模板", "API 接入", "专属支持"],
    cta: "即将上线",
    active: false,
  },
];

export function PricingPage(): JSX.Element {
  return (
    <section className="space-y-10 py-8">
      <header className="text-center">
        <h1 className="text-h1 text-foreground">定价方案</h1>
        <p className="mt-2 text-caption text-foreground-muted">选择适合你的方案，随时升级。</p>
      </header>

      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => (
          <div
            key={plan.name}
            className={`rounded-lg border p-6 ${plan.active ? "border-primary/30 bg-primary/[0.03]" : "border-white/[0.06] bg-surface"}`}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-h3 font-semibold text-foreground">{plan.name}</h3>
              {plan.active && <Badge variant="default">当前</Badge>}
            </div>
            <p className="mt-2 text-h2 font-semibold text-foreground">{plan.price}</p>
            <ul className="mt-4 space-y-2">
              {plan.features.map((f) => (
                <li key={f} className="flex items-center gap-2 text-caption text-foreground-muted">
                  <Check className="h-3.5 w-3.5 text-success" />
                  {f}
                </li>
              ))}
            </ul>
            <Button className="mt-6 w-full" variant={plan.active ? "default" : "secondary"} disabled={!plan.active}>
              {plan.cta}
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
