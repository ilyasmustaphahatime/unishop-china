export default function ProgressSteps({ current, total }: { current: number; total: number }) {
  return (
    <div aria-label={`Step ${current} of ${total}`}>
      <div className="mb-2 flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-500">
        <span>Getting started</span>
        <span>{current} / {total}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-red-600 transition-all"
          style={{ width: `${Math.round((current / total) * 100)}%` }}
        />
      </div>
    </div>
  );
}
