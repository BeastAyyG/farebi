interface SkeletonProps {
  className?: string;
}

function Bar({ className = '' }: SkeletonProps) {
  return <div className={`a-skeleton rounded-[6px] ${className}`} />;
}

/**
 * Shape-of-the-answer loading state.
 *
 * A spinner tells the reviewer "wait"; this tells them what is coming and
 * stops the layout jumping when it lands. Marked `aria-hidden` because the
 * live region already announces "Analysing capture" — a screen reader should
 * not have to sit through a described placeholder.
 */
export function ResultSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-5">
      {/* Verdict card */}
      <div className="card overflow-hidden">
        <div className="flex">
          <div className="a-skeleton w-1 shrink-0" />
          <div className="flex-1 p-4">
            <div className="flex items-center gap-3">
              <Bar className="h-7 w-7 rounded-full" />
              <Bar className="h-5 w-40" />
            </div>
            <Bar className="mt-3 h-3 w-2/3" />
          </div>
        </div>
        <div className="space-y-3 p-4">
          <Bar className="h-4 w-11/12" />
          <Bar className="h-3 w-full rounded-full" />
          <Bar className="h-10 w-full rounded-[8px]" />
        </div>
      </div>

      {/* Signal rows */}
      <div className="card space-y-3 p-4">
        <Bar className="h-4 w-44" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-[10px] border border-line p-3">
            <div className="flex items-center justify-between gap-2">
              <Bar className="h-5 w-32" />
              <Bar className="h-4 w-24" />
            </div>
            <Bar className="mt-3 h-2 w-full rounded-full" />
            <Bar className="mt-3 h-3 w-4/5" />
          </div>
        ))}
      </div>
    </div>
  );
}
