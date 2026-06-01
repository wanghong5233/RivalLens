export type RunStatus = "running" | "completed" | "degraded" | "failed" | string;

export interface RunCreateRequest {
  user_query: string;
  competitors: string[];
  domain_hint?: string | null;
  reference_urls?: string[] | null;
  target_roles: string[];
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
  domain_hint: string | null;
  reference_urls: string[];
  status: RunStatus;
  target_roles: string[];
  competitors: string[];
  started_at: string;
  finished_at: string | null;
  created_at: string;
}

export interface RunListItemResponse {
  run_id: string;
  user_query: string;
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

export interface AgentStatusResponse {
  agent_name: string;
  role: string;
  status: string;
  task_count: number;
  success_rate: number;
  avg_latency_ms: number;
}

export interface DashboardMetricsResponse {
  total_runs: number;
  running_runs: number;
  completed_runs: number;
  failed_runs: number;
  total_evidence: number;
  total_llm_calls: number;
  total_tokens: number;
  avg_run_duration_seconds: number | null;
  overall_success_rate: number;
}

export interface DataSourceDistribution {
  source_type: string;
  count: number;
  percentage: number;
}

export interface DailyRunStats {
  date: string;
  count: number;
  avg_duration_seconds: number | null;
}

export interface DashboardResponse {
  metrics: DashboardMetricsResponse;
  agent_status: AgentStatusResponse[];
  source_distribution: DataSourceDistribution[];
  daily_stats: DailyRunStats[];
}
