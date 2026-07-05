"use client";

interface FollowButtonProps {
  followed: boolean;
  pending: boolean;
  onToggle: () => void;
}

export default function FollowButton({ followed, pending, onToggle }: FollowButtonProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={pending}
      aria-pressed={followed}
      className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
        followed
          ? "bg-indigo-600 text-white hover:bg-indigo-500"
          : "border border-indigo-600 text-indigo-600 hover:bg-indigo-50"
      }`}
    >
      {pending ? "…" : followed ? "Following" : "Follow"}
    </button>
  );
}
