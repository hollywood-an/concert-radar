"use client";

interface FollowButtonProps {
  followed: boolean;
  pending: boolean;
  onToggle: () => void;
}

// Highlighter is the colour for "yours" across the app, so a followed artist's button
// matches the date stubs of their shows.
export default function FollowButton({ followed, pending, onToggle }: FollowButtonProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={pending}
      aria-pressed={followed}
      className={`inline-flex min-w-[5.5rem] items-center justify-center rounded-full border px-4 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
        followed
          ? "border-highlighter-deep bg-highlighter text-ink hover:bg-highlighter-deep"
          : "border-ink/25 bg-sheet text-ink hover:border-ink"
      }`}
    >
      {pending ? "…" : followed ? "Following" : "Follow"}
    </button>
  );
}
