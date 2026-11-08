// Shared button styles (class strings, so links and buttons can share them).

const base =
  "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";

export const buttonPrimary = `${base} bg-sky-700 text-white hover:bg-sky-800 dark:bg-sky-500 dark:text-zinc-950 dark:hover:bg-sky-400`;

export const buttonSecondary = `${base} border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900`;
