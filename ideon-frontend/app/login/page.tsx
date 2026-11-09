"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { useAuth } from "../auth-provider";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await login({ email: email.trim(), password });
      const next = searchParams.get("next");
      router.replace(next && next.startsWith("/") ? next : "/");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to sign in. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center px-5 py-16 sm:py-24">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#8E2638]">
            IDEON · ACADEMY WORKSPACE
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#F5F2EE]">
            Sign in
          </h1>
          <p className="mt-2 text-sm text-[#A6A1A0]">
            Enter your credentials to reach your private workspace.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-[#77777D]/20 bg-[#222124]/70 p-6 shadow-xl sm:p-8"
        >
          {error && (
            <p
              role="alert"
              className="mb-5 rounded border border-[#8E2638]/40 bg-[#8E2638]/10 px-3 py-2 text-sm text-[#E58A9B]"
            >
              {error}
            </p>
          )}

          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#A6A1A0]">
              Email
            </span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-2 w-full rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2.5 text-sm text-[#F5F2EE] outline-none transition-colors focus:border-[#8E2638]"
              placeholder="you@example.com"
            />
          </label>

          <label className="mt-5 block">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#A6A1A0]">
              Password
            </span>
            <div className="relative mt-2">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2.5 pr-16 text-sm text-[#F5F2EE] outline-none transition-colors focus:border-[#8E2638]"
                placeholder="Your password"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute inset-y-0 right-0 px-3 font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0] hover:text-[#F5F2EE]"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="mt-7 w-full rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2.5 font-mono text-xs uppercase tracking-[0.16em] text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>

          <p className="mt-6 text-center text-sm text-[#A6A1A0]">
            New to Ideon?{" "}
            <Link
              href="/register"
              className="text-[#E58A9B] underline-offset-4 hover:underline"
            >
              Create an account
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
