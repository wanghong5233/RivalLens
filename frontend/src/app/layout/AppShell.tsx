import { Outlet } from "react-router-dom";

export function AppShell(): JSX.Element {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-6xl items-center px-4">
          <span className="text-sm font-semibold tracking-wide">RivalLens Console</span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
