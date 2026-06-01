export type RunStatus = "running" | "completed" | "degraded" | "failed" | string;

export type RunPhase = "intake" | "planning" | "executing" | "done";

export type UserRole = "pm" | "founder" | "sales" | "investor";

export interface RunCreateRequest {
  user_query: string;
  competitors: string[];
  domain_hint?: string | null;
  reference_urls?: string[] | null;
  target_roles: string[];
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
  report_depth: "quick" | "deep";
  reference_urls: string[];
  is_complete: boolean;
}

export interface IntakeClarifyRequest {
  question: string;
  field_targets: string[];
  suggested_options: string[] | null;
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
  report_depth?: "quick" | "deep";
}

export interface IntakeCreateResponse {
  run_id: string;
  status: RunStatus;
  phase: RunPhase;
  intake_draft: RunIntakeDraft;
  first_clarify_request: IntakeClarifyRequest | null;
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

export interface RunTraceResponse {
  run: RunDetailResponse;
  steps: StepTraceResponse[];
  supervisor_decisions: SupervisorDecisionTraceResponse[];
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
  source_type_distribution: Record<string, number>;
  desensitization_coverage: number;
  qa_total_steps: number;
  qa_rejected_steps: number;
  qa_rejection_rate: number;
  supervisor_iterations: number;
  llm_token_total: number;
  llm_call_count: number;
  llm_latency_p50_ms: number | null;
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

export interface WatchlistItemResponse {
  watch_id: string;
  competitor_id: string;
  note: string | null;
  next_refresh_at: string | null;
  created_at: string;
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
