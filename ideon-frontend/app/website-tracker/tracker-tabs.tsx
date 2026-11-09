"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/website-tracker/calendar", label: "CALENDAR" },
  { href: "/website-tracker/urls", label: "URL LIBRARY" },
];

export function TrackerTabs() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-2" aria-label="Website Tracker sections">
      {tabs.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`rounded border px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors ${
              active
                ? "border-[#8E2638]/60 bg-[#8E2638]/20 text-[#E58A9B]"
                : "border-[#77777D]/25 bg-[#1C1B1E] text-[#A6A1A0] hover:border-[#77777D]/50 hover:text-[#F5F2EE]"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
