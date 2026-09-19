"use client";

import { Sidebar } from "@/components/Sidebar";

/** Left sidebar plus a content column. The page decides what fills the column. */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
