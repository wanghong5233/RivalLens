import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { useCreateWatchlistItem, useDeleteWatchlistItem, useWatchlist } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { pushToast } from "@/components/ui/toaster";

export function WatchPage(): JSX.Element {
  const [newCompetitor, setNewCompetitor] = useState("");
  const watchlistQuery = useWatchlist();
  const createMutation = useCreateWatchlistItem();
  const deleteMutation = useDeleteWatchlistItem();

  async function handleAdd(): Promise<void> {
    const id = newCompetitor.trim();
    if (!id) return;
    try {
      await createMutation.mutateAsync({ competitor_id: id });
      setNewCompetitor("");
      pushToast({ title: `已添加 ${id}`, variant: "success" });
    } catch (error) {
      if (error instanceof Error) pushToast({ title: "添加失败", description: error.message, variant: "danger" });
    }
  }

  async function handleDelete(watchId: string): Promise<void> {
    try {
      await deleteMutation.mutateAsync(watchId);
      pushToast({ title: "已移除", variant: "success" });
    } catch (error) {
      if (error instanceof Error) pushToast({ title: "移除失败", description: error.message, variant: "danger" });
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-h1 text-foreground">竞品追踪</h1>
        <p className="mt-1 text-caption text-foreground-muted">添加竞品到追踪列表，持续监控更新动态。</p>
      </header>

      <div className="flex gap-2">
        <Input
          placeholder="输入竞品名称..."
          value={newCompetitor}
          onChange={(e) => setNewCompetitor(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void handleAdd(); }}
        />
        <Button onClick={() => void handleAdd()} disabled={createMutation.isPending}>
          <Plus className="h-4 w-4" />
          添加
        </Button>
      </div>

      {watchlistQuery.isLoading && <Skeleton className="h-32 w-full" />}

      {watchlistQuery.data && watchlistQuery.data.length === 0 && (
        <div className="rounded-lg border border-white/[0.06] bg-surface p-8 text-center text-caption text-foreground-muted">
          追踪列表为空，添加竞品开始持续监控。
        </div>
      )}

      <div className="space-y-1">
        {(watchlistQuery.data ?? []).map((item) => (
          <div key={item.watch_id} className="flex items-center justify-between rounded-md px-3 py-2.5 hover:bg-white/[0.03]">
            <div>
              <p className="text-caption font-medium text-foreground">{item.competitor_id}</p>
              {item.note && <p className="text-micro text-foreground-subtle">{item.note}</p>}
            </div>
            <Button size="icon" variant="ghost" onClick={() => void handleDelete(item.watch_id)} aria-label="移除">
              <Trash2 className="h-3.5 w-3.5 text-foreground-muted" />
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
