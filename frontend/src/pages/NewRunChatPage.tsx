import {
  Bot,
  CheckCircle2,
  Circle,
  Loader2,
  Sparkles,
  User as UserIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { useCreateRunIntake, useReplyRunIntake } from "@/api/hooks";
import {
  useRunEvents,
  type IntakeClarifyEventPayload,
  type IntakeCompletePayload,
} from "@/api/sse";
import type {
  IntakeClarifyRequest,
  IntakeCreateRequest,
  IntakeUserReply,
  RunDetailResponse,
  RunIntakeDraft,
  UserRole,
} from "@/api/types";
import { IntakeModeSwitcher } from "@/components/intake/IntakeModeSwitcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { pushToast } from "@/components/ui/toaster";

// --- Message model --------------------------------------------------------

type ChatMessage =
  | { id: string; kind: "assistant.welcome"; text: string }
  | {
      id: string;
      kind: "assistant.clarify";
      question: string;
      fieldTargets: string[];
      suggestedOptions: string[];
    }
  | { id: string; kind: "assistant.complete"; text: string }
  | { id: string; kind: "assistant.error"; text: string }
  | { id: string; kind: "user"; text: string; selectedOptions: string[] };

type ChatStatus =
  | "idle"
  | "creating"
  | "awaiting_user"
  | "replying"
  | "resuming"
  | "complete"
  | "error";

const WELCOME_TEXT =
  "你好，我是 RivalLens。告诉我你想分析的问题，我会先帮你确认目标和竞品范围，再开始抓取证据。";

const POST_COMPLETE_DELAY_MS = 1500;

// --- Helpers --------------------------------------------------------------

function newMessageId(): string {
  return `msg_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 8)}`;
}

function emptyDraft(userQuery: string): RunIntakeDraft {
  return {
    user_query: userQuery,
    user_role: null,
    analysis_intent: null,
    competitors_explicit: [],
    competitors_discovery_mode: false,
    domain_hint: null,
    focus_dimensions: [],
    report_depth: "quick",
    reference_urls: [],
    is_complete: false,
  };
}

function clarifyMessageFromPayload(
  payload: Pick<IntakeClarifyRequest, "question" | "field_targets"> & {
    suggested_options: string[] | null;
  },
): ChatMessage {
  return {
    id: newMessageId(),
    kind: "assistant.clarify",
    question: payload.question,
    fieldTargets: [...(payload.field_targets ?? [])],
    suggestedOptions: payload.suggested_options ? [...payload.suggested_options] : [],
  };
}

function deriveChecklistRows(draft: RunIntakeDraft | null): Array<{
  id: string;
  label: string;
  hint: string;
  satisfied: boolean;
}> {
  return [
    {
      id: "identity",
      label: "用户身份",
      hint:
        draft?.user_role !== null && draft?.user_role !== undefined
          ? roleLabel(draft.user_role)
          : "PM / 创业者 / 销售 / 投资人",
      satisfied: draft?.user_role !== null && draft?.user_role !== undefined,
    },
    {
      id: "intent",
      label: "分析意图",
      hint:
        draft?.analysis_intent !== null && draft?.analysis_intent !== undefined
          ? draft.analysis_intent
          : "你最希望解决的问题或决策",
      satisfied: Boolean(draft?.analysis_intent),
    },
    {
      id: "competitors",
      label: "竞品范围",
      hint: competitorHint(draft),
      satisfied: competitorPathSatisfied(draft),
    },
  ];
}

function roleLabel(role: UserRole): string {
  switch (role) {
    case "pm":
      return "产品经理";
    case "founder":
      return "创业者";
    case "sales":
      return "销售";
    case "investor":
      return "投资人";
    default:
      return role;
  }
}

function competitorHint(draft: RunIntakeDraft | null): string {
  if (!draft) {
    return "指定竞品或让 Agent 自动发现";
  }
  if (draft.competitors_explicit.length > 0) {
    return draft.competitors_explicit.join("、");
  }
  if (draft.competitors_discovery_mode) {
    return "由 Agent 自动发现赛道头部";
  }
  return "指定竞品或让 Agent 自动发现";
}

function competitorPathSatisfied(draft: RunIntakeDraft | null): boolean {
  if (!draft) {
    return false;
  }
  return draft.competitors_explicit.length > 0 || draft.competitors_discovery_mode;
}

// --- Page ------------------------------------------------------------------

export function NewRunChatPage(): JSX.Element {
  const navigate = useNavigate();
  const createIntake = useCreateRunIntake();
  const replyIntake = useReplyRunIntake();

  const [runId, setRunId] = useState<string | null>(null);
  const [draft, setDraft] = useState<RunIntakeDraft | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    { id: "welcome", kind: "assistant.welcome", text: WELCOME_TEXT },
  ]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [composerText, setComposerText] = useState("");
  const [composerOptions, setComposerOptions] = useState<string[]>([]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll the chat thread to the latest message.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const currentClarify = useMemo<ChatMessage | null>(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const msg = messages[i];
      if (msg.kind === "assistant.clarify") {
        return msg;
      }
    }
    return null;
  }, [messages]);

  // --- SSE: clarify_request / complete --------------------------------------

  const refreshDraftFromBackend = useCallback(
    async (refRunId: string) => {
      try {
        const { data } = await apiClient.get<RunDetailResponse>(`/api/runs/${refRunId}`);
        if (data.intake_draft) {
          setDraft(data.intake_draft);
        }
      } catch {
        // Draft refresh is best-effort. The checklist will catch up on the next
        // event. Avoid spamming the user with toast on transient network errors.
      }
    },
    [setDraft],
  );

  const handleIntakeClarify = useCallback(
    (payload: IntakeClarifyEventPayload) => {
      setMessages((prev) => [
        ...prev,
        clarifyMessageFromPayload({
          question: payload.question,
          field_targets: payload.field_targets,
          suggested_options: payload.suggested_options,
        }),
      ]);
      setStatus("awaiting_user");
      setComposerOptions([]);
      if (runId !== null) {
        void refreshDraftFromBackend(runId);
      }
    },
    [runId, refreshDraftFromBackend],
  );

  const handleIntakeComplete = useCallback(
    (payload: IntakeCompletePayload) => {
      const draftFromEvent = payload.draft as Partial<RunIntakeDraft> | undefined;
      if (draftFromEvent) {
        setDraft({
          ...emptyDraft(draftFromEvent.user_query ?? ""),
          ...draftFromEvent,
          is_complete: true,
        });
      }
      setMessages((prev) => [
        ...prev,
        {
          id: newMessageId(),
          kind: "assistant.complete",
          text: "需求确认完成，Agent 正在为你拟定一份分析计划，请稍候确认。",
        },
      ]);
      setStatus("complete");
      pushToast({
        title: "需求确认完成",
        description: "正在跳转到计划确认页…",
        variant: "success",
      });
      if (runId !== null) {
        const targetRunId = runId;
        // Phase 2: hand off to PlanConfirmPage. The planner publishes a plan
        // shortly after intake completes; PlanConfirmPage either renders the
        // already-mirrored Run.plan_tree or waits for plan.published over SSE.
        window.setTimeout(() => {
          navigate(`/app/runs/${targetRunId}/plan`);
        }, POST_COMPLETE_DELAY_MS);
      }
    },
    [runId, navigate],
  );

  useRunEvents(runId ?? "", {
    onIntakeClarify: handleIntakeClarify,
    onIntakeComplete: handleIntakeComplete,
  });

  // --- Send handlers --------------------------------------------------------

  const canSend = useMemo(() => {
    if (status === "creating" || status === "replying" || status === "resuming" || status === "complete") {
      return false;
    }
    if (runId === null) {
      // Initial create: require non-empty query.
      return composerText.trim().length > 0;
    }
    // Reply: require at least non-empty text OR a selected option.
    return composerText.trim().length > 0 || composerOptions.length > 0;
  }, [status, runId, composerText, composerOptions]);

  async function handleSend(): Promise<void> {
    if (!canSend) {
      return;
    }
    if (runId === null) {
      await startIntake(composerText.trim());
      return;
    }
    await sendReply(composerText.trim(), composerOptions);
  }

  async function startIntake(userQuery: string): Promise<void> {
    setStatus("creating");
    const userMessage: ChatMessage = {
      id: newMessageId(),
      kind: "user",
      text: userQuery,
      selectedOptions: [],
    };
    setMessages((prev) => [...prev, userMessage]);
    setComposerText("");
    try {
      const payload: IntakeCreateRequest = { user_query: userQuery };
      const response = await createIntake.mutateAsync(payload);
      setRunId(response.run_id);
      setDraft(response.intake_draft);
      if (response.first_clarify_request !== null) {
        const clarify = response.first_clarify_request;
        setMessages((prev) => [
          ...prev,
          clarifyMessageFromPayload({
            question: clarify.question,
            field_targets: clarify.field_targets,
            suggested_options: clarify.suggested_options,
          }),
        ]);
        setStatus("awaiting_user");
        return;
      }
      // Backend returned phase=done immediately. Navigate to the run page.
      setStatus("complete");
      pushToast({
        title: "已开始分析",
        description: "需求一次就明确，直接跳到运行详情。",
        variant: "success",
      });
      const targetRunId = response.run_id;
      window.setTimeout(() => navigate(`/app/runs/${targetRunId}`), POST_COMPLETE_DELAY_MS);
    } catch (error) {
      const message = error instanceof Error ? error.message : "未知错误";
      setMessages((prev) => [
        ...prev,
        {
          id: newMessageId(),
          kind: "assistant.error",
          text: `创建任务失败：${message}`,
        },
      ]);
      setStatus("error");
      pushToast({
        title: "创建任务失败",
        description: message,
        variant: "danger",
      });
    }
  }

  async function sendReply(text: string, selectedOptions: string[]): Promise<void> {
    if (runId === null) {
      return;
    }
    if (text.length === 0 && selectedOptions.length === 0) {
      return;
    }
    setStatus("replying");
    const userMessage: ChatMessage = {
      id: newMessageId(),
      kind: "user",
      text,
      selectedOptions: [...selectedOptions],
    };
    setMessages((prev) => [...prev, userMessage]);
    setComposerText("");
    setComposerOptions([]);
    try {
      const reply: IntakeUserReply = { text, selected_options: selectedOptions };
      await replyIntake.mutateAsync({ runId, reply });
      setStatus("resuming");
    } catch (error) {
      const message = error instanceof Error ? error.message : "未知错误";
      setMessages((prev) => [
        ...prev,
        {
          id: newMessageId(),
          kind: "assistant.error",
          text: `回复失败：${message}`,
        },
      ]);
      setStatus("awaiting_user");
      pushToast({
        title: "回复失败",
        description: message,
        variant: "danger",
      });
    }
  }

  function toggleOption(option: string): void {
    setComposerOptions((prev) => {
      if (prev.includes(option)) {
        return prev.filter((item) => item !== option);
      }
      return [...prev, option];
    });
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await handleSend();
  }

  const checklistRows = useMemo(() => deriveChecklistRows(draft), [draft]);
  const isBusy =
    status === "creating" || status === "replying" || status === "resuming";
  const composerDisabled = isBusy || status === "complete";
  const composerPlaceholder =
    runId === null
      ? "例如：对比 Cursor、Windsurf 与 TRAE 在产品定位、付费转化和用户口碑上的差异"
      : "回答 Agent 的问题，或补充更多上下文…";

  return (
    <section className="space-y-5">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-h1 text-foreground">新建竞品分析</h1>
          <IntakeModeSwitcher active="chat" />
        </div>
        <p className="text-caption text-foreground-muted">
          告诉 Agent 你想分析什么，我会用对话帮你确认身份、意图和竞品范围，再开始抓取证据。
          想跳过澄清直接填表单，可以切到「专家表单」。
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <Card className="flex h-[28rem] flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="inline-flex items-center gap-2 text-lg">
                <Sparkles className="h-4 w-4 text-primary" />
                Agent 对话
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-2 overflow-hidden pt-0">
              <div className="flex-1 space-y-3 overflow-y-auto pr-2">
                {messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    onOptionToggle={toggleOption}
                    selectedOptions={composerOptions}
                    isCurrentClarify={currentClarify?.id === message.id}
                  />
                ))}
                {isBusy && <ThinkingBubble status={status} />}
                <div ref={messagesEndRef} />
              </div>
            </CardContent>
          </Card>

          <form onSubmit={handleSubmit}>
            <Card className="border-primary/30">
              <CardContent className="space-y-2 p-4">
                <textarea
                  aria-label="向 Agent 输入"
                  className="min-h-20 w-full resize-none rounded-md border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-caption text-foreground outline-none transition focus:border-primary/40 focus:ring-2 focus:ring-ring/40"
                  disabled={composerDisabled}
                  onChange={(event) => setComposerText(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  placeholder={composerPlaceholder}
                  value={composerText}
                />
                {composerOptions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {composerOptions.map((option) => (
                      <Badge key={option} variant="secondary" className="text-xs">
                        已选：{option}
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-muted-foreground">
                    回车发送，Shift+Enter 换行。
                    {status === "resuming"
                      ? " Agent 正在思考下一个问题…"
                      : ""}
                  </p>
                  <Button disabled={!canSend} size="sm" type="submit">
                    {isBusy ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        发送中
                      </>
                    ) : (
                      "发送"
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </form>
        </div>

        <aside className="space-y-3">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="inline-flex items-center gap-2 text-base">
                <CheckCircle2 className="h-4 w-4 text-primary" />
                需求清单
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 pt-0">
              {checklistRows.map((row) => (
                <ChecklistItem
                  key={row.id}
                  label={row.label}
                  hint={row.hint}
                  satisfied={row.satisfied}
                />
              ))}
              {draft !== null && (
                <div className="space-y-1 rounded-md border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-foreground-muted">
                  {draft.domain_hint && (
                    <p>
                      <span className="text-foreground-subtle">领域：</span>
                      {draft.domain_hint}
                    </p>
                  )}
                  {draft.focus_dimensions.length > 0 && (
                    <p>
                      <span className="text-foreground-subtle">关注维度：</span>
                      {draft.focus_dimensions.join("、")}
                    </p>
                  )}
                  <p>
                    <span className="text-foreground-subtle">报告深度：</span>
                    {draft.report_depth === "deep" ? "深度报告" : "速览"}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">为什么要对话？</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0 text-xs text-foreground-muted">
              <p>
                Agent 会先与你对齐角色、意图和竞品范围，再开始抓取证据——
                这样可以避免「报告生成了但方向错」的浪费。
              </p>
              <p>
                如果你已经清楚自己要什么，可以切到「专家表单」一次性填完。
              </p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </section>
  );
}

// --- Subcomponents --------------------------------------------------------

interface MessageBubbleProps {
  message: ChatMessage;
  selectedOptions: string[];
  onOptionToggle: (option: string) => void;
  isCurrentClarify: boolean;
}

function MessageBubble({
  message,
  selectedOptions,
  onOptionToggle,
  isCurrentClarify,
}: MessageBubbleProps): JSX.Element {
  if (message.kind === "user") {
    return (
      <div className="flex items-start gap-2 justify-end">
        <div className="max-w-[80%] rounded-lg rounded-tr-sm bg-primary/15 px-3 py-2 text-sm text-foreground">
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
          {message.selectedOptions.length > 0 && (
            <p className="mt-1 text-xs text-foreground-muted">
              已选项：{message.selectedOptions.join("、")}
            </p>
          )}
        </div>
        <div className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
          <UserIcon className="h-3.5 w-3.5" />
        </div>
      </div>
    );
  }

  const Icon = message.kind === "assistant.error" ? Sparkles : Bot;
  const bubbleColor =
    message.kind === "assistant.error"
      ? "bg-danger/10 text-danger"
      : message.kind === "assistant.complete"
        ? "bg-success/10 text-success"
        : "bg-white/[0.04] text-foreground";

  return (
    <div className="flex items-start gap-2">
      <div className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/[0.05] text-primary">
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className={cn("max-w-[80%] rounded-lg rounded-tl-sm px-3 py-2 text-sm", bubbleColor)}>
        {message.kind === "assistant.clarify" ? (
          <>
            <p className="whitespace-pre-wrap break-words">{message.question}</p>
            {message.fieldTargets.length > 0 && (
              <p className="mt-1 text-xs text-foreground-muted">
                关于：{message.fieldTargets.join("、")}
              </p>
            )}
            {message.suggestedOptions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {message.suggestedOptions.map((option) => {
                  const isSelected =
                    isCurrentClarify && selectedOptions.includes(option);
                  return (
                    <button
                      aria-pressed={isSelected}
                      className={cn(
                        "rounded-full border px-3 py-1 text-xs transition",
                        isSelected
                          ? "border-primary/60 bg-primary/15 text-foreground"
                          : "border-white/[0.1] bg-white/[0.03] text-foreground-muted hover:border-primary/40 hover:text-foreground",
                        !isCurrentClarify && "opacity-60",
                      )}
                      disabled={!isCurrentClarify}
                      key={option}
                      onClick={() => onOptionToggle(option)}
                      type="button"
                    >
                      {option}
                    </button>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
        )}
      </div>
    </div>
  );
}

function ThinkingBubble({ status }: { status: ChatStatus }): JSX.Element {
  const label =
    status === "creating"
      ? "正在创建任务…"
      : status === "replying"
        ? "已发送，等待 Agent…"
        : "Agent 正在思考下一个问题…";
  return (
    <div className="flex items-start gap-2">
      <div className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/[0.05] text-primary">
        <Bot className="h-3.5 w-3.5" />
      </div>
      <div className="inline-flex items-center gap-2 rounded-lg rounded-tl-sm bg-white/[0.04] px-3 py-2 text-sm text-foreground-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {label}
      </div>
    </div>
  );
}

interface ChecklistItemProps {
  label: string;
  hint: string;
  satisfied: boolean;
}

function ChecklistItem({ label, hint, satisfied }: ChecklistItemProps): JSX.Element {
  return (
    <div className="flex items-start gap-2">
      {satisfied ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
      ) : (
        <Circle className="mt-0.5 h-4 w-4 shrink-0 text-foreground-subtle" />
      )}
      <div className="min-w-0">
        <p
          className={cn(
            "text-sm font-medium",
            satisfied ? "text-foreground" : "text-foreground-muted",
          )}
        >
          {label}
        </p>
        <p className="text-xs text-foreground-muted">{hint}</p>
      </div>
    </div>
  );
}
