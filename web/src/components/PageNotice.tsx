"use client";

import Link from "next/link";

import { useSessionReady } from "@/app/providers";
import NavBar from "@/components/NavBar";

export function PageNotice({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto min-h-screen max-w-4xl p-6">
      <NavBar />
      <div className="mt-10 text-center text-sm text-slate-500">{children}</div>
    </main>
  );
}

// Pages that need a session show this while signed out; the login form lives on the Feed.
export function SignInNotice({ purpose }: { purpose: string }) {
  const sessionReady = useSessionReady();
  return (
    <PageNotice>
      {sessionReady ? (
        <>
          <Link href="/" className="font-medium text-indigo-600 hover:underline">
            Sign in
          </Link>{" "}
          to {purpose}.
        </>
      ) : (
        "Loading…"
      )}
    </PageNotice>
  );
}
