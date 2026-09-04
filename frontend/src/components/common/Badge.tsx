import type { PropsWithChildren } from 'react';

export default function Badge({ children, positive = false }: PropsWithChildren<{ positive?: boolean }>) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ${
        positive ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'
      }`}
    >
      {children}
    </span>
  );
}
