"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "../auth-provider";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      await register({
        username: username.trim(),
        email: email.trim(),
        password,
        confirm_password: confirmPassword,
      });
      router.replace("/");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to create the account. Please try again.",
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
            Create your account
          </h1>
          <p className="mt-2 text-sm text-[#A6A1A0]">
            Your ideas and assessments stay private to this account.
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
              Username
            </span>
            <input
              type="text"
              autoComplete="username"
              required
              minLength={3}
              maxLength={32}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="mt-2 w-full rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2.5 text-sm text-[#F5F2EE] outline-none transition-colors focus:border-[#8E2638]"
              placeholder="your-handle"
            />
          </label>

          <label className="mt-5 block">
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
                autoComplete="new-password"
                required
                minLength={12}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2.5 pr-16 text-sm text-[#F5F2EE] outline-none transition-colors focus:border-[#8E2638]"
                placeholder="At least 12 characters"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute inset-y-0 right-0 px-3 font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0] hover:text-[#F5F2EE]"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <span className="mt-1.5 block text-[11px] text-[#77777D]">
              Use at least 12 characters with a letter and a number.
            </span>
          </label>

          <label className="mt-5 block">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#A6A1A0]">
              Confirm password
            </span>
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              minLength={12}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              className="mt-2 w-full rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2.5 text-sm text-[#F5F2EE] outline-none transition-colors focus:border-[#8E2638]"
              placeholder="Repeat your password"
            />
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="mt-7 w-full rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2.5 font-mono text-xs uppercase tracking-[0.16em] text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>

          <p className="mt-6 text-center text-sm text-[#A6A1A0]">
            Already registered?{" "}
            <Link
              href="/login"
              className="text-[#E58A9B] underline-offset-4 hover:underline"
            >
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
