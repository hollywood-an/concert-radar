import { dateParts } from "@/lib/format";

// The stub's colour says whose show this is: highlighter for an artist the user follows,
// pink for a match that just arrived, plain otherwise.
export type StubTone = "plain" | "following" | "fresh";

const TONES: Record<StubTone, string> = {
  plain: "",
  following: "!bg-highlighter",
  fresh: "!bg-pink !text-white",
};

interface DateStubProps {
  iso: string;
  tone?: StubTone;
  large?: boolean;
}

// The date end of a ticket: month, day, weekday, and the year when it isn't this year.
export default function DateStub({ iso, tone = "plain", large = false }: DateStubProps) {
  const { month, day, weekday, year } = dateParts(iso);
  return (
    <time dateTime={iso} className={`ticket-stub ${TONES[tone]} ${large ? "py-6" : "py-3"}`}>
      <span
        className={`font-display font-bold uppercase leading-none tracking-wide ${
          large ? "text-base sm:text-xl" : "text-sm"
        }`}
      >
        {month}
      </span>
      <span
        className={`font-display font-black leading-none ${
          large ? "text-5xl sm:text-7xl" : "text-[2.5rem]"
        }`}
      >
        {day}
      </span>
      <span
        className={`mt-1 font-medium leading-none ${large ? "text-xs sm:text-sm" : "text-[11px]"} ${
          tone === "fresh" ? "text-white/90" : "text-ink-soft"
        }`}
      >
        {weekday}
        {year !== null && ` ${year}`}
      </span>
    </time>
  );
}
