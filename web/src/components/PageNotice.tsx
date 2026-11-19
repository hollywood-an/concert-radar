"use client";

import Link from "next/link";

import { useSessionReady } from "@/app/providers";
import NavBar from "@/components/NavBar";

export function PageNotice({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-6 sm:px-6">
      <NavBar />
      <div className="mt-16 text-center text-ink-soft">{children}</div>
    </main>
  );
}

// Pages that need a session show this while signed out; the sign-in form is on the Feed.
export function SignInNotice({ purpose }: { purpose: string }) {
  const sessionReady = useSessionReady();
  return (
    <PageNotice>
      {sessionReady ? (
        <>
          <Link href="/" className="link">
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
