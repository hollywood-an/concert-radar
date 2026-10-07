const STATUS_STYLES: Record<string, string> = {
  on_sale: "bg-green-100 text-green-800",
  announced: "bg-amber-100 text-amber-800",
  cancelled: "bg-red-100 text-red-800",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 font-medium ${
        STATUS_STYLES[status] ?? "bg-slate-100 text-slate-700"
      }`}
    >
      {status.replace("_", " ")}
    </span>
  );
}
