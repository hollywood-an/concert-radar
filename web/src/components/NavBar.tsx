"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import RadarMark from "@/components/RadarMark";
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
    <header className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b-2 border-ink pb-4">
      <Link
        href="/"
        className="flex items-center gap-2 font-display text-[1.75rem] font-black uppercase leading-none"
      >
        <RadarMark className="h-7 w-7" />
        Concert Radar
      </Link>
      <nav aria-label="Main" className="flex items-center gap-1 text-sm font-semibold">
        {LINKS.map((link) => {
          const current = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={current ? "page" : undefined}
              className={`rounded-full px-3 py-1.5 transition-colors ${
                current ? "bg-ink text-white" : "text-ink-soft hover:text-ink"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      {live && (
        <span
          className="flex items-center gap-1.5 text-xs font-semibold text-emerald-800"
          title="New matches appear in your feed as soon as they are found"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500 motion-reduce:animate-none" />
          Live
        </span>
      )}
      {user && (
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="hidden max-w-[14rem] truncate text-ink-soft md:inline">
            {user.email}
          </span>
          <button
            type="button"
            onClick={() => {
              dispatch(loggedOut());
              dispatch(feedCleared());
              dispatch(followsCleared());
            }}
            className="font-semibold text-ink underline-offset-4 hover:text-pink hover:underline"
          >
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}
