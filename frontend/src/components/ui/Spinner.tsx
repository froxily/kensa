export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-muted">
      <span
        aria-hidden="true"
        className="size-4 animate-spin rounded-full border-2 border-zinc-300 border-t-sky-500 motion-reduce:animate-none dark:border-zinc-700"
      />
      {label}
    </span>
  );
}
