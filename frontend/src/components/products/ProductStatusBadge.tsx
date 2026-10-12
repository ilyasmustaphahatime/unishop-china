import type { OwnProduct } from '../../features/products/types';
export default function ProductStatusBadge({ status }: { status: OwnProduct['status'] }) {
  return <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">{status}</span>;
}
