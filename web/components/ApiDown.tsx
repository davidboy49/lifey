export function ApiDown() {
  return (
    <div className="card hatch mx-auto mt-16 max-w-lg p-8 text-center">
      <p className="font-display text-2xl font-semibold">Can’t reach the Lifey API</p>
      <p className="mt-2 text-ink-2">
        Start it with <code className="rounded bg-panel px-1.5 py-0.5 font-mono text-sm">docker compose up</code>, or run{" "}
        <code className="rounded bg-panel px-1.5 py-0.5 font-mono text-sm">uvicorn app.main:app</code> in <code className="font-mono text-sm">api/</code>.
      </p>
    </div>
  );
}
