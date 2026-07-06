"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { loggedOut } from "@/store/authSlice";
import { feedCleared } from "@/store/feedSlice";
import { followsCleared } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

const LINKS = [
  { href: "/", label: "Feed" },
  { href: "/map", label: "Map" },
  { href: "/settings", label: "Settings" },
];

export default function NavBar({ live = false }: { live?: boolean }) {
  const pathname = usePathname();
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.auth.user);

  return (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-6">
        <h1 className="text-2xl font-bold text-slate-900">Concert Radar</h1>
        <nav className="flex items-center gap-4 text-sm font-medium">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                pathname === link.href
                  ? "text-indigo-600"
                  : "text-slate-500 hover:text-slate-900"
              }
            >
              {link.label}
            </Link>
          ))}
        </nav>
        {live && (
          <span className="flex items-center gap-1.5 text-xs font-medium text-green-600">
            <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
            live
          </span>
        )}
      </div>
      {user && (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>{user.email}</span>
          <button
            type="button"
            onClick={() => {
              dispatch(loggedOut());
              dispatch(feedCleared());
              dispatch(followsCleared());
            }}
            className="font-medium text-indigo-600 hover:underline"
          >
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}
