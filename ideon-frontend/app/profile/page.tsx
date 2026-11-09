"use client";

import { useRouter } from "next/navigation";

import { formatDate } from "@/lib/api";
import { useAuth } from "../auth-provider";

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const router = useRouter();

  if (!user) {
    return null;
  }

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  const rows = [
    { label: "Username", value: user.username },
    { label: "Email", value: user.email },
    {
      label: "Account role",
      value: user.role === "admin" ? "Administrator" : "Member",
    },
    { label: "Created", value: formatDate(user.created_at) },
  ];

  return (
    <div className="flex flex-1 justify-center px-5 py-14 sm:py-20">
      <div className="w-full max-w-xl">
        <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#8E2638]">
          ACCOUNT
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#F5F2EE]">
          Your profile
        </h1>
        <p className="mt-2 text-sm text-[#A6A1A0]">
          Account details for this Ideon workspace.
        </p>

        <dl className="mt-8 divide-y divide-[#222124] overflow-hidden rounded-xl border border-[#77777D]/20 bg-[#222124]/70">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex flex-wrap items-baseline justify-between gap-3 px-5 py-4"
            >
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#A6A1A0]">
                {row.label}
              </dt>
              <dd className="text-sm text-[#F5F2EE]">{row.value}</dd>
            </div>
          ))}
        </dl>

        <button
          type="button"
          onClick={handleLogout}
          className="mt-8 w-full rounded border border-[#8E2638]/60 bg-[#171719] px-4 py-2.5 font-mono text-xs uppercase tracking-[0.16em] text-[#E58A9B] transition-colors hover:border-[#8E2638] hover:text-[#F5F2EE]"
        >
          Log out
        </button>
      </div>
    </div>
  );
}
