import { Boxes, ExternalLink, MessageSquareQuote, Tags, UserRound } from "lucide-react";
import { useMemo } from "react";

import type {
  KnowledgeFeedback,
  KnowledgeFeature,
  KnowledgePersona,
  KnowledgePricing,
  RunKnowledgeResponse,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface KnowledgePanelProps {
  knowledge: RunKnowledgeResponse | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  onEvidenceClick: (evidenceIds: string[]) => void;
  compact?: boolean;
}

const MATURITY_LABELS: Record<NonNullable<KnowledgeFeature["maturity"]>, string> = {
  unknown: "未知",
  basic: "基础",
  advanced: "成熟",
  leading: "领先",
};

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.trim().length > 0)));
}

function getCompetitorIds(knowledge: RunKnowledgeResponse | null): string[] {
  if (knowledge === null) {
    return [];
  }
  return unique([
    ...knowledge.features.map((item) => item.competitor_id),
    ...knowledge.pricings.map((item) => item.competitor_id),
    ...knowledge.feedback.map((item) => item.competitor_id),
    ...Object.keys(knowledge.coverage),
  ]);
}

function groupFeatures(features: KnowledgeFeature[]): Map<string, KnowledgeFeature[]> {
  const grouped = new Map<string, KnowledgeFeature[]>();
  for (const feature of features) {
    const items = grouped.get(feature.competitor_id) ?? [];
    items.push(feature);
    grouped.set(feature.competitor_id, items);
  }
  return grouped;
}

function groupPricings(pricings: KnowledgePricing[]): Map<string, KnowledgePricing[]> {
  const grouped = new Map<string, KnowledgePricing[]>();
  for (const pricing of pricings) {
    const items = grouped.get(pricing.competitor_id) ?? [];
    items.push(pricing);
    grouped.set(pricing.competitor_id, items);
  }
  return grouped;
}

function groupFeedback(items: KnowledgeFeedback[]): Map<string, KnowledgeFeedback[]> {
  const grouped = new Map<string, KnowledgeFeedback[]>();
  for (const item of items) {
    const rows = grouped.get(item.competitor_id) ?? [];
    rows.push(item);
    grouped.set(item.competitor_id, rows);
  }
  return grouped;
}

function EvidenceButton({
  evidenceIds,
  onEvidenceClick,
}: {
  evidenceIds: string[];
  onEvidenceClick: (evidenceIds: string[]) => void;
}): JSX.Element | null {
  if (evidenceIds.length === 0) {
    return null;
  }
  return (
    <Button
      className="h-7 px-2 text-micro"
      onClick={() => onEvidenceClick(evidenceIds)}
      size="sm"
      type="button"
      variant="outline"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {evidenceIds.length} 条证据
    </Button>
  );
}

function EmptyBlock({ text }: { text: string }): JSX.Element {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
      {text}
    </div>
  );
}

function SchemaStat({
  hint,
  label,
  value,
}: {
  hint: string;
  label: string;
  value: number;
}): JSX.Element {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-surface/70 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground">{value.toLocaleString()}</p>
      <p className="mt-1 text-xs text-foreground-subtle">{hint}</p>
    </div>
  );
}

function FeatureTree({
  competitorId,
  features,
  onEvidenceClick,
}: {
  competitorId: string;
  features: KnowledgeFeature[];
  onEvidenceClick: (evidenceIds: string[]) => void;
}): JSX.Element {
  const byParent = new Map<string, KnowledgeFeature[]>();
  const ids = new Set(features.map((feature) => feature.id));
  for (const feature of features) {
    const parentKey = feature.parent_id && ids.has(feature.parent_id) ? feature.parent_id : "root";
    const items = byParent.get(parentKey) ?? [];
    items.push(feature);
    byParent.set(parentKey, items);
  }
  const roots = byParent.get("root") ?? [];

  return (
    <section className="rounded-lg border border-border bg-background/50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-foreground">{competitorId}</h4>
        <Badge variant="secondary">{features.length} 项功能</Badge>
      </div>
      <div className="space-y-2">
        {roots.map((feature) => (
          <FeatureNode
            childrenByParent={byParent}
            feature={feature}
            key={feature.id}
            level={0}
            onEvidenceClick={onEvidenceClick}
          />
        ))}
      </div>
    </section>
  );
}

function FeatureNode({
  childrenByParent,
  feature,
  level,
  onEvidenceClick,
}: {
  childrenByParent: Map<string, KnowledgeFeature[]>;
  feature: KnowledgeFeature;
  level: number;
  onEvidenceClick: (evidenceIds: string[]) => void;
}): JSX.Element {
  const children = childrenByParent.get(feature.id) ?? [];
  const maturity = feature.maturity ? MATURITY_LABELS[feature.maturity] : null;
  return (
    <div className={cn("rounded-md border border-white/[0.06] bg-surface/70 p-3", level > 0 && "ml-4")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{feature.name}</p>
            {maturity ? <Badge variant="secondary">{maturity}</Badge> : null}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{feature.description}</p>
        </div>
        <EvidenceButton evidenceIds={feature.evidence_ids} onEvidenceClick={onEvidenceClick} />
      </div>
      {children.length > 0 ? (
        <div className="mt-2 space-y-2">
          {children.map((child) => (
            <FeatureNode
              childrenByParent={childrenByParent}
              feature={child}
              key={child.id}
              level={Math.min(level + 1, 2)}
              onEvidenceClick={onEvidenceClick}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PricingBlock({
  pricing,
  onEvidenceClick,
}: {
  pricing: KnowledgePricing;
  onEvidenceClick: (evidenceIds: string[]) => void;
}): JSX.Element {
  const tiers = Array.isArray(pricing.tiers) ? pricing.tiers : [];
  return (
    <article className="rounded-md border border-white/[0.06] bg-surface/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">{pricing.model || "unknown"}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge variant={pricing.free_plan ? "success" : "secondary"}>
              {pricing.free_plan ? "有免费版" : "免费版未知/无"}
            </Badge>
            <Badge variant={pricing.enterprise_plan ? "success" : "secondary"}>
              {pricing.enterprise_plan ? "企业版" : "企业版未知/无"}
            </Badge>
          </div>
        </div>
        <EvidenceButton evidenceIds={pricing.evidence_ids} onEvidenceClick={onEvidenceClick} />
      </div>
      {tiers.length > 0 ? (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {tiers.map((tier, index) => {
            const tierName = typeof tier.name === "string" && tier.name.trim() ? tier.name : "未命名套餐";
            const limits = Array.isArray(tier.limits) ? tier.limits : [];
            return (
            <div className="rounded border border-border bg-background/50 p-2" key={`${pricing.id}-${tierName}-${index.toString(10)}`}>
              <p className="text-xs font-medium text-foreground">{tierName}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {tier.price ?? "价格未知"} {tier.unit ?? ""}
              </p>
              {limits.length > 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">{limits.join(" · ")}</p>
              ) : null}
            </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">未提取到分层价格。</p>
      )}
    </article>
  );
}

function PersonaBlock({
  persona,
  onEvidenceClick,
}: {
  persona: KnowledgePersona;
  onEvidenceClick: (evidenceIds: string[]) => void;
}): JSX.Element {
  return (
    <article className="rounded-md border border-white/[0.06] bg-surface/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">{persona.name}</p>
          <p className="mt-1 text-xs text-muted-foreground">{persona.role}</p>
        </div>
        <EvidenceButton evidenceIds={persona.evidence_ids} onEvidenceClick={onEvidenceClick} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <ListBlock items={persona.pain_points} title="痛点" />
        <ListBlock items={persona.jobs_to_be_done} title="任务" />
      </div>
    </article>
  );
}

function FeedbackBlock({
  feedback,
  onEvidenceClick,
}: {
  feedback: KnowledgeFeedback;
  onEvidenceClick: (evidenceIds: string[]) => void;
}): JSX.Element {
  return (
    <article className="rounded-md border border-white/[0.06] bg-surface/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">{feedback.topic}</p>
          <p className="mt-1 text-xs text-muted-foreground">{feedback.sentiment}</p>
        </div>
        <EvidenceButton evidenceIds={feedback.evidence_ids} onEvidenceClick={onEvidenceClick} />
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{feedback.summary}</p>
    </article>
  );
}

function ListBlock({ items, title }: { items: string[]; title: string }): JSX.Element {
  return (
    <div>
      <p className="text-xs font-medium text-foreground">{title}</p>
      {items.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">暂无</p>
      ) : (
        <ul className="mt-1 space-y-1 text-xs leading-5 text-muted-foreground">
          {items.map((item, index) => (
            <li key={`${item}-${index.toString(10)}`}>- {item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function KnowledgePanel({
  knowledge,
  isLoading = false,
  errorMessage = null,
  onEvidenceClick,
  compact = false,
}: KnowledgePanelProps): JSX.Element {
  const featureGroups = useMemo(() => groupFeatures(knowledge?.features ?? []), [knowledge?.features]);
  const pricingGroups = useMemo(() => groupPricings(knowledge?.pricings ?? []), [knowledge?.pricings]);
  const feedbackGroups = useMemo(() => groupFeedback(knowledge?.feedback ?? []), [knowledge?.feedback]);
  const competitorIds = useMemo(() => getCompetitorIds(knowledge), [knowledge]);
  const featureCount = knowledge?.features.length ?? 0;
  const pricingCount = knowledge?.pricings.length ?? 0;
  const personaCount = knowledge?.personas.length ?? 0;
  const feedbackCount = knowledge?.feedback.length ?? 0;
  const hasKnowledge =
    featureCount + pricingCount + personaCount + feedbackCount > 0;

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (errorMessage !== null) {
    return (
      <div className="rounded-lg border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
        竞品知识读取失败：{errorMessage}
      </div>
    );
  }

  return (
    <div className={cn("space-y-5", compact && "space-y-4")}>
      <div>
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-foreground">
            <Boxes className="h-4 w-4 text-primary" />
            竞品知识总览
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            基于已采集公开证据抽取的功能、定价、用户画像与用户反馈。
          </p>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <SchemaStat hint="功能树节点" label="功能树" value={featureCount} />
        <SchemaStat hint="套餐/商业模式" label="定价模型" value={pricingCount} />
        <SchemaStat hint="目标角色与 JTBD" label="用户画像" value={personaCount} />
        <SchemaStat hint="口碑与体验主题" label="用户反馈" value={feedbackCount} />
      </div>

      {!hasKnowledge ? (
        <EmptyBlock
          text="当前暂无可展示的竞品知识。通常是公开证据不足、目标信息未公开，或抽取仍在处理中。"
        />
      ) : null}

      <section className="space-y-3">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Boxes className="h-4 w-4 text-primary" />
          功能树
        </h4>
        {competitorIds.length === 0 || knowledge?.features.length === 0 ? (
          <EmptyBlock
            text="暂无功能树条目：可能是公开证据不足、产品未公开，或抽取仍在处理中。"
          />
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {competitorIds.map((competitorId) => {
              const items = featureGroups.get(competitorId) ?? [];
              return items.length > 0 ? (
                <FeatureTree
                  competitorId={competitorId}
                  features={items}
                  key={competitorId}
                  onEvidenceClick={onEvidenceClick}
                />
              ) : null;
            })}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Tags className="h-4 w-4 text-primary" />
          定价模型
        </h4>
        {competitorIds.length === 0 || knowledge?.pricings.length === 0 ? (
          <EmptyBlock
            text="暂无定价模型条目：可能是价格未公开、证据不足，或抽取仍在处理中。"
          />
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {competitorIds.map((competitorId) => {
              const items = pricingGroups.get(competitorId) ?? [];
              return items.length > 0 ? (
                <section className="rounded-lg border border-border bg-background/50 p-4" key={competitorId}>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-foreground">{competitorId}</h4>
                    <Badge variant="secondary">{items.length} 个模型</Badge>
                  </div>
                  <div className="space-y-2">
                    {items.map((pricing) => (
                      <PricingBlock
                        key={pricing.id}
                        onEvidenceClick={onEvidenceClick}
                        pricing={pricing}
                      />
                    ))}
                  </div>
                </section>
              ) : null;
            })}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <UserRound className="h-4 w-4 text-primary" />
          用户画像
        </h4>
        {knowledge?.personas.length === 0 ? (
          <EmptyBlock
            text="暂无用户画像条目：可能是公开资料未覆盖目标用户，或抽取仍在处理中。"
          />
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {(knowledge?.personas ?? []).map((persona) => (
              <PersonaBlock
                key={persona.id}
                onEvidenceClick={onEvidenceClick}
                persona={persona}
              />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <MessageSquareQuote className="h-4 w-4 text-primary" />
          用户反馈
        </h4>
        {competitorIds.length === 0 || knowledge?.feedback.length === 0 ? (
          <EmptyBlock
            text="暂无用户反馈条目：可能是公开评论证据不足，或抽取仍在处理中。"
          />
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {competitorIds.map((competitorId) => {
              const items = feedbackGroups.get(competitorId) ?? [];
              return items.length > 0 ? (
                <section className="rounded-lg border border-border bg-background/50 p-4" key={`${competitorId}-feedback`}>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-foreground">{competitorId}</h4>
                    <Badge variant="secondary">{items.length} 条反馈</Badge>
                  </div>
                  <div className="space-y-2">
                    {items.map((feedback) => (
                      <FeedbackBlock
                        feedback={feedback}
                        key={feedback.id}
                        onEvidenceClick={onEvidenceClick}
                      />
                    ))}
                  </div>
                </section>
              ) : null;
            })}
          </div>
        )}
      </section>
    </div>
  );
}
