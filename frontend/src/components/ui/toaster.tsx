import { useSyncExternalStore } from "react";

import { Toast } from "@/components/ui/toast";

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant?: "default" | "success" | "warning" | "danger";
}

const listeners = new Set<() => void>();
let items: ToastItem[] = [];

function emit(): void {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): ToastItem[] {
  return items;
}

function removeToast(id: string): void {
  items = items.filter((item) => item.id !== id);
  emit();
}

export interface PushToastInput {
  title: string;
  description?: string;
  variant?: "default" | "success" | "warning" | "danger";
  durationMs?: number;
}

export function pushToast(input: PushToastInput): void {
  const toastItem: ToastItem = {
    id: `toast_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
    title: input.title,
    description: input.description,
    variant: input.variant ?? "default",
  };
  items = [toastItem, ...items].slice(0, 4);
  emit();

  const durationMs = input.durationMs ?? 3500;
  window.setTimeout(() => {
    removeToast(toastItem.id);
  }, durationMs);
}

export function Toaster(): JSX.Element {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
      {snapshot.map((item) => (
        <div className="pointer-events-auto" key={item.id}>
          <Toast description={item.description} title={item.title} variant={item.variant} />
        </div>
      ))}
    </div>
  );
}
