"use client";

import NavBar from "@/components/NavBar";
import { useAppSelector } from "@/store/hooks";

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
  const status = useAppSelector((state) => state.auth.status);
  return (
    <PageNotice>
      {status === "idle" ? `Sign in on the Feed page to ${purpose}.` : "Loading…"}
    </PageNotice>
  );
}
