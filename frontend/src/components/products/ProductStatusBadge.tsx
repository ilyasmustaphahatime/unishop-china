import { productStatusKeys } from '../../i18n/labels';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import type { OwnProduct } from '../../features/products/types';
export default function ProductStatusBadge({ status }: { status: OwnProduct['status'] }) {
  const { t } = useAppTranslation();
  return <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">{t(productStatusKeys[status])}</span>;
}
