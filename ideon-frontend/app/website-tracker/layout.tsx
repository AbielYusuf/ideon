import type { ReactNode } from "react";
import { Suspense } from "react";

import AdminGuard from "./admin-guard";
import { TrackerTabs } from "./tracker-tabs";

export default function WebsiteTrackerLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <AdminGuard>
      <div className="academy-grid relative flex min-h-screen flex-1 flex-col overflow-hidden bg-[#171719] text-[#F5F2EE]">
        <div className="w-full ruler-ticks border-b border-[#222124] opacity-40" />

        <main className="relative mx-auto w-full max-w-6xl flex-1 px-5 py-8 sm:px-8 sm:py-10">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-[#222124] pb-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#8E2638]">
                EOS · WEBSITE OPERATIONS
              </p>
              <h1 className="mt-1 font-mono text-2xl font-semibold tracking-[0.14em] text-[#F5F2EE] sm:text-3xl">
                WEBSITE TRACKER
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#A6A1A0]">
                Document planned and completed website work, and keep a complete
                activity history for every imported URL.
              </p>
            </div>
            <Suspense fallback={null}>
              <TrackerTabs />
            </Suspense>
          </div>

          {children}
        </main>
      </div>
    </AdminGuard>
  );
}
