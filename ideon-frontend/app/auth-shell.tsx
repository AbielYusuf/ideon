"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "./auth-provider";

const PUBLIC_PATHS = new Set(["/login", "/register"]);

function Navigation() {
  const { user, logout } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <nav className="border-b border-[#222124] bg-[#171719]/95 backdrop-blur-sm sticky top-0 z-50">
      <div className="mx-auto max-w-5xl px-5 flex flex-wrap items-center gap-x-4 gap-y-2 py-3 sm:gap-6">
        <Link
          href={user ? "/" : "/login"}
          className="font-mono text-xs font-semibold text-[#F5F2EE] tracking-widest hover:text-white transition-colors"
        >
          IDEON
        </Link>
        <span className="text-[#77777D]/30 select-none">|</span>

        {user ? (
          <>
            <Link
              href="/"
              className="font-mono text-xs text-[#A6A1A0] hover:text-[#F5F2EE] transition-colors tracking-wider"
            >
              IDEA ARCHIVE
            </Link>
            <Link
              href="/quick-access"
              className="font-mono text-xs text-[#A6A1A0] hover:text-[#F5F2EE] transition-colors tracking-wider"
            >
              QUICK ACCESS
            </Link>
            {user.role === "admin" && (
              <Link
                href="/website-tracker/calendar"
                className="font-mono text-xs text-[#A6A1A0] hover:text-[#F5F2EE] transition-colors tracking-wider"
              >
                WEBSITE TRACKER
              </Link>
            )}
            <span className="ml-auto flex items-center gap-3">
              <Link
                href="/profile"
                className="font-mono text-xs text-[#E58A9B] hover:text-[#F5F2EE] transition-colors tracking-wider"
              >
                {user.username.toUpperCase()}
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="font-mono text-xs text-[#A6A1A0] hover:text-[#F5F2EE] transition-colors tracking-wider"
              >
                LOG OUT
              </button>
            </span>
          </>
        ) : (
          <span className="ml-auto flex items-center gap-4">
            <Link
              href="/login"
              className="font-mono text-xs text-[#A6A1A0] hover:text-[#F5F2EE] transition-colors tracking-wider"
            >
              SIGN IN
            </Link>
            <Link
              href="/register"
              className="font-mono text-xs text-[#E58A9B] hover:text-[#F5F2EE] transition-colors tracking-wider"
            >
              REGISTER
            </Link>
          </span>
        )}
      </div>
    </nav>
  );
}

function LoadingPanel({ message }: { message: string }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-24">
      <div className="text-center">
        <div
          className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-[#222124] border-t-[#8E2638]"
          aria-hidden
        />
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-[#77777D]">
          {message}
        </p>
      </div>
    </div>
  );
}

export default function AuthShell({ children }: { children: ReactNode }) {
  const { user, loading, error, refresh } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.has(pathname ?? "");

  useEffect(() => {
    // Wait until the route is resolved before deciding whether it is public.
    if (!pathname) {
      return;
    }
    // Redirect to login once session check completes and there is no authenticated user.
    if (isPublic || loading || user) {
      return;
    }
    const next = pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/login${next}`);
  }, [error, isPublic, loading, pathname, router, user]);

  return (
    <>
      <Navigation />
      {isPublic ? (
        children
      ) : loading ? (
        <LoadingPanel message="Verifying session" />
      ) : user ? (
        children
      ) : error ? (
        <div className="flex flex-1 items-center justify-center px-6 py-24">
          <div className="max-w-md rounded-lg border border-[#8E2638]/40 bg-[#222124]/70 p-8 text-center">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#8E2638]">
              CONNECTION ERROR
            </p>
            <h1 className="mt-3 text-xl font-semibold text-[#F5F2EE]">
              Backend unavailable
            </h1>
            <p className="mt-2 text-sm leading-6 text-[#A6A1A0]">{error}</p>
            <button
              type="button"
              onClick={() => refresh()}
              className="mt-6 rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-5 py-2 font-mono text-xs uppercase tracking-wider text-white transition-opacity hover:opacity-90"
            >
              Retry
            </button>
          </div>
        </div>
      ) : (
        <LoadingPanel message="Redirecting to sign in" />
      )}
    </>
  );
}
