/** Terminal run status; `degraded` means the report finished with known quality issues. */
export type RunStatus = "running" | "completed" | "degraded" | "failed" | string;

export type RunPhase = "intake" | "planning" | "executing" | "done";

export type UserRole = "pm" | "founder" | "sales" | "investor";
export type ReportDepth = "debug" | "quick" | "deep";

export interface RunCreateRequest {
  user_query: string;
  competitors: string[];
  domain_hint?: string | null;
  reference_urls?: string[] | null;
  target_roles: string[];
  report_depth?: ReportDepth;
  self_product?: string | null;
  market_scope?: string | null;
  time_context?: string | null;
}

// --- Phase 1/2 Agent-native intake + plan-then-execute contract ---

export interface RunIntakeDraft {
  user_query: string;
  user_role: UserRole | null;
  analysis_intent: string | null;
  competitors_explicit: string[];
  competitors_discovery_mode: boolean;
  domain_hint: string | null;
  focus_dimensions: string[];
  report_depth: ReportDepth;
  reference_urls: string[];
  self_product: string | null;
  market_scope: string | null;
  time_context: string | null;
  is_complete: boolean;
}

export interface IntakeClarifyRequest {
  question: string;
  field_targets: string[];
  suggested_options: string[] | null;
  suggested_answer: string | null;
}

export interface IntakeUserReply {
  text: string;
  selected_options: string[];
}

export interface IntakeCreateRequest {
  user_query: string;
  user_role?: UserRole | null;
  domain_hint?: string | null;
  reference_urls?: string[] | null;
  competitors_explicit?: string[];
  competitors_discovery_mode?: boolean;
  focus_dimensions?: string[];
  report_depth?: ReportDepth;
}

export interface IntakeCreateResponse {
  run_id: string;
  status: RunStatus;
  phase: RunPhase;
  intake_draft: RunIntakeDraft;
  first_clarify_request?: IntakeClarifyRequest | null;
}

export interface IntakeExchange {
  clarify: IntakeClarifyRequest;
  reply: IntakeUserReply;
}

export interface IntakeSessionResponse {
  run_id: string;
  status: RunStatus;
  phase: RunPhase | null;
  awaiting_user: boolean;
  intake_draft: RunIntakeDraft | null;
  pending_clarify: IntakeClarifyRequest | null;
  history: IntakeExchange[];
}

export type PlanTaskStage = "discover" | "research" | "analyze" | "write";

export interface PlanTask {
  task_id: string;
  stage: PlanTaskStage;
  title: string;
  description: string;
  competitor_id: string | null;
  focus_dimensions: string[];
  source: "agent" | "user";
  enabled: boolean;
  priority: "normal" | "user_pinned";
}

export interface PlanTree {
  plan_id: string;
  tasks: PlanTask[];
  rationale: string;
  version: number;
  // ISO timestamp; null until planner_wait resumes from the user's confirmation.
  confirmed_at: string | null;
  competitor_sources?: Record<
    string,
    {
      official_url: string | null;
      source_domain: string | null;
    }
  >;
}

export interface PlanConfirmRequest {
  disabled_task_ids: string[];
  additional_tasks: PlanTask[];
}

export interface FollowUpRequest {
  text: string;
  applies_to_stage?: PlanTaskStage | null;
}

export interface FollowUpAcceptedResponse {
  run_id: string;
  follow_up_id: string;
  received_at: string;
}

export interface RunAcceptedResponse {
  run_id: string;
  status: RunStatus;
}

export interface RunCreateResponse {
  run_id: string;
  status: RunStatus;
  message: string;
}

export interface RunResetRequest {
  reset_to: "analyst" | "writer";
}

export interface RunDetailResponse {
  run_id: string;
  user_query: string;
  // LLM-generated short label populated at intake.complete. Null for legacy
  // runs and the brief window before intake completes; UI must fall back to
  // truncating user_query in that case (see `formatRunTitle`).
  title: string | null;
  domain_hint: string | null;
  reference_urls: string[];
  status: RunStatus;
  target_roles: string[];
  competitors: string[];
  started_at: string;
  finished_at: string | null;
  created_at: string;
  // Phase 1+ (optional until the backend detail handler + migration land).
  phase?: RunPhase;
  intake_draft?: RunIntakeDraft | null;
  plan_tree?: PlanTree | null;
}

export interface RunListItemResponse {
  run_id: string;
  user_query: string;
  title: string | null;
  domain_hint: string | null;
  status: RunStatus;
  phase?: RunPhase | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  step_count: number;
  evidence_count: number;
  has_report: boolean;
}

export interface RunListResponse {
  items: RunListItemResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface StepTraceResponse {
  step_id: string;
  run_id: string;
  agent_name: string;
  status: string;
  retry_count: number;
  payload: Record<string, unknown>;
  rejection_reason: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
}

export interface SupervisorDecisionTraceResponse {
  id: string;
  run_id: string;
  iteration: number;
  chosen_tool: string;
  tool_args: Record<string, unknown>;
  reasoning_summary: string;
  triggered_by: string | null;
  outcome: string | null;
  outcome_recorded_at: string | null;
  created_at: string;
}

export interface LLMCallTraceResponse {
  id: number;
  step_id: string;
  model_slot: string;
  provider: string | null;
  model_name: string | null;
  prompt_hash: string | null;
  prompt_preview: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  error: string | null;
  retry_count: number;
  fallback_used: boolean | null;
  fallback_reason: string | null;
  created_at: string;
}

export interface TraceTimelineItemResponse {
  kind: "step" | "decision" | "llm_call";
  timestamp: string;
  step_id: string | null;
  agent_name: string | null;
  summary: string;
  payload: Record<string, unknown>;
}

export interface RunTraceResponse {
  run: RunDetailResponse;
  steps: StepTraceResponse[];
  supervisor_decisions: SupervisorDecisionTraceResponse[];
  llm_calls: LLMCallTraceResponse[];
  timeline: TraceTimelineItemResponse[];
}

export interface EvidenceBriefResponse {
  evidence_id: string;
  source_type: string;
  source_url: string | null;
  source_title: string | null;
  competitor_id: string | null;
}

export interface RunReportResponse {
  run_id: string;
  status: RunStatus;
  content_markdown: string;
  content_json: Record<string, unknown>;
  generated_at: string;
  evidence_id_to_brief: Record<string, EvidenceBriefResponse>;
}

export interface RunMetricsResponse {
  run_id: string;
  coverage_rate: number;
  evidence_count_total: number;
  evidence_count_by_competitor: Record<string, number>;
  evidence_count_by_dimension: Record<string, number>;
  comparison_dimensions: string[];
  conclusion_sections: string[];
  report_section_ids: string[];
  dimension_coverage_rate: number;
  evidence_dimension_coverage_rate: number;
  report_char_count: number;
  report_section_count: number;
  report_depth: ReportDepth;
  report_section_coverage_rate: number;
  knowledge_feature_count: number;
  knowledge_pricing_count: number;
  knowledge_persona_count: number;
  knowledge_schema_coverage_rate: number;
  source_type_distribution: Record<string, number>;
  source_authority_distribution: Record<string, number>;
  locale_match_rate: number;
  locale_distribution: Record<string, number>;
  desensitization_coverage: number;
  qa_total_steps: number;
  qa_rejected_steps: number;
  qa_rejection_rate: number;
  supervisor_iterations: number;
  llm_token_total: number;
  llm_call_count: number;
  llm_latency_p50_ms: number | null;
  llm_provider_error_count: number;
  llm_retry_total: number;
  manual_review_rate: number;
  manual_review_is_proxy: boolean;
  run_wall_clock_seconds: number | null;
}

export interface ConclusionItemResponse {
  conclusion_id: string;
  run_id: string;
  step_id: string;
  section: string;
  claim: string;
  confidence: string;
  competitor_ids: string[];
  risk_flags: string[];
  evidence_ids: string[];
  created_at: string;
}

export interface RunConclusionsResponse {
  run_id: string;
  items: ConclusionItemResponse[];
}

export type KnowledgeFeatureMaturity = "unknown" | "basic" | "advanced" | "leading" | null;

export interface KnowledgeFeature {
  id: string;
  competitor_id: string;
  name: string;
  parent_id: string | null;
  description: string;
  maturity: KnowledgeFeatureMaturity;
  evidence_ids: string[];
}

export interface KnowledgePricingTier {
  name?: string;
  price?: string | null;
  unit?: string | null;
  limits?: string[];
}

export interface KnowledgePricing {
  id: string;
  competitor_id: string;
  model: string;
  tiers: KnowledgePricingTier[];
  free_plan: boolean | null;
  enterprise_plan: boolean | null;
  evidence_ids: string[];
}

export interface KnowledgePersona {
  id: string;
  name: string;
  role: string;
  pain_points: string[];
  jobs_to_be_done: string[];
  evidence_ids: string[];
}

export type KnowledgeFeedbackSentiment = "positive" | "neutral" | "negative" | "mixed";

export interface KnowledgeFeedback {
  id: string;
  competitor_id: string;
  sentiment: KnowledgeFeedbackSentiment;
  topic: string;
  summary: string;
  evidence_ids: string[];
}

export interface RunKnowledgeResponse {
  run_id: string;
  analysis_archetype: "comparison" | "landscape" | string;
  schema_version: string;
  features: KnowledgeFeature[];
  pricings: KnowledgePricing[];
  personas: KnowledgePersona[];
  feedback: KnowledgeFeedback[];
  missing_reasons: Record<string, string[]>;
  coverage: Record<string, Record<string, string>>;
}

export type ComparisonStance = "leader" | "competitive" | "laggard" | "unknown" | string;

export interface ComparisonCellResponse {
  cell_id: string;
  run_id: string;
  step_id: string;
  dimension: string;
  competitor_id: string;
  stance: ComparisonStance;
  summary: string;
  evidence_ids: string[];
  created_at: string;
}

export interface DimensionComparisonResponse {
  dimension: string;
  cells: ComparisonCellResponse[];
}

export interface RunComparisonsResponse {
  run_id: string;
  items: DimensionComparisonResponse[];
}

export interface WatchlistItemResponse {
  watch_id: string;
  competitor_id: string;
  note: string | null;
  next_refresh_at: string | null;
  created_at: string;
}

export interface WatchInsightItemResponse {
  conclusion_id: string;
  run_id: string;
  run_title: string;
  section: string;
  claim: string;
  confidence: string;
  evidence_ids: string[];
  created_at: string;
}

export interface WatchlistDigestItemResponse {
  watch_id: string;
  competitor_id: string;
  note: string | null;
  created_at: string;
  insight_count: number;
  run_count: number;
  last_updated_at: string | null;
  latest_run_id: string | null;
  items: WatchInsightItemResponse[];
}

export interface WatchlistCreateRequest {
  competitor_id: string;
  note?: string | null;
  next_refresh_at?: string | null;
}

export interface EvidenceListItemResponse {
  evidence_id: string;
  run_id: string;
  source_type: string;
  source_url: string | null;
  source_title: string | null;
  sanitized_text: string;
  competitor_id: string | null;
  metadata: Record<string, unknown> | null;
  desensitized: boolean;
  collected_at: string;
  created_at: string;
}

export interface CompetitorSeedResponse {
  id: string;
  display_name: string;
  aliases: string[];
  official_url: string | null;
  category: string | null;
}

export interface SkillCandidateResponse {
  id: string;
  candidate_type: string;
  applies_to: string;
  tags: string[];
  payload: Record<string, unknown>;
  rationale: string;
  supporting_run_ids: string[];
  confidence: "low" | "medium" | "high" | string;
  status: "staging" | "approved" | "rejected" | string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  error: string | null;
  created_at: string;
}

export interface SkillCandidateListResponse {
  items: SkillCandidateResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface SkillCandidateReviewRequest {
  reviewed_by: string;
}

export interface SkillCandidateReviewResponse {
  id: string;
  status: string;
  reviewed_by: string;
  reviewed_at: string;
  promoted_artifacts: PromotedArtifactResponse[];
}

export interface PromotedArtifactResponse {
  path: string;
  action: "created" | "updated" | string;
  entry_id: string;
}
