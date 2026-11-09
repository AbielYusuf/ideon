"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useAuth } from "../auth-provider";

export default function AdminGuard({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  if (user?.role !== "admin") {
    return (
      <div className="mx-auto w-full max-w-2xl px-5 py-20 text-center">
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#8E2638]">
          ADMINISTRATOR ACCESS REQUIRED
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-[#F5F2EE]">
          Website Tracker is restricted
        </h2>
        <p className="mt-3 text-sm leading-6 text-[#A6A1A0]">
          This operational workspace is available to administrator accounts
          only. Your personal ideas and assessments are unaffected.
        </p>
        <Link
          href="/"
          className="mt-7 inline-block rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-5 py-2.5 font-mono text-xs uppercase tracking-wider text-white transition-opacity hover:opacity-90"
        >
          Back to idea archive
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
