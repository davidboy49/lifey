import { StatementDrop } from "@/components/StatementDrop";

export default function MoneyPage() {
  return (
    <div className="flex flex-col gap-8">
      <header>
        <p className="eyebrow">Money</p>
        <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">
          Bank statements
        </h1>
        <p className="mt-2 max-w-[60ch] text-ink-2">
          Import an ABA statement and it lands in Sure. Money lives in its own module with its own data, separate from
          your health history.
        </p>
      </header>
      <StatementDrop />
    </div>
  );
}
