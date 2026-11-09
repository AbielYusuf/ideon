import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";

import { AuthProvider } from "./auth-provider";
import AuthShell from "./auth-shell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "IDEON · ACADEMY WORKSPACE",
  description: "Your ideas, refined — AI-powered Japanese Academy Workspace.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full dark antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[#171719] text-[#F5F2EE] font-sans selection:bg-[#8E2638] selection:text-white">
        <AuthProvider>
          <Suspense fallback={null}>
            <AuthShell>{children}</AuthShell>
          </Suspense>
        </AuthProvider>
      </body>
    </html>
  );
}
