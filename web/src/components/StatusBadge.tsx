import { formatStatus } from "@/lib/format";

const STATUS_STYLES: Record<string, string> = {
  on_sale: "bg-emerald-100 text-emerald-900",
  announced: "bg-amber-100 text-amber-900",
  postponed: "bg-amber-100 text-amber-900",
  rescheduled: "bg-amber-100 text-amber-900",
  cancelled: "bg-red-100 text-red-900",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
        STATUS_STYLES[status] ?? "bg-paper text-ink-soft"
      }`}
    >
      {formatStatus(status)}
    </span>
  );
}
