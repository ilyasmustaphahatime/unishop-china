import { conditionKeys } from '../../i18n/labels';
import { catalogName, formatCurrency, formatListingTimestamp } from '../../i18n/formatters';
import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { useState } from 'react';
import { Link } from 'react-router';
import Alert from '../../components/common/Alert';
import Button from '../../components/common/Button';
import Spinner from '../../components/common/Spinner';
import ProductStatusBadge from '../../components/products/ProductStatusBadge';
import { useMyProducts } from '../../features/products/hooks';
import { productErrorMessage } from '../../features/products/api';

export default function SellerProductsPage() {
  const { t } = useAppTranslation();
  const [offset, setOffset] = useState(0);
  const query = useMyProducts(offset);
  return <section>
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="text-3xl font-black">{t('common:myListings')}</h1>
      <Link className="rounded-xl bg-red-600 px-4 py-3 font-semibold text-white" to="/sell/new">{t('common:newListing')}</Link>
    </div>
    <p className="my-4 text-slate-600">{t('products:privateListCopy')}</p>
    {query.isPending && <Spinner label={t('products:loadingList')} />}
    {query.isError && <Alert>{localizeMessage(productErrorMessage(query.error))} <button onClick={() => void query.refetch()}>{t('products:retryList')}</button></Alert>}
    {query.data && !query.isError && <>
      {!query.data.items.length && <p role="status">{t('products:noListings')}</p>}
      <ul className="space-y-3">{query.data.items.map((p) => <li key={p.public_slug} className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link className="font-bold text-red-700 underline" to={'/seller/listings/' + p.public_slug + '/edit'}><bdi>{p.title}</bdi></Link>
          <ProductStatusBadge status={p.status} />
        </div>
        <p className="mt-2"><bdi>{formatCurrency(p.price)}</bdi> · <bdi>{catalogName(p.city)}</bdi> · <bdi>{catalogName(p.category)}</bdi></p>
        <p className="mt-1 text-sm text-slate-600">{t('products:conditionLine', { condition: t(conditionKeys[p.condition]) })}</p>
        <p className="text-sm text-slate-600"><time dateTime={p.updated_at}>{t('products:updated', { date: formatListingTimestamp(p.updated_at) })}</time></p>
        {(!p.city_active || !p.category_active) && <p className="text-sm text-amber-800">{t('products:retiredCatalog')}</p>}
      </li>)}</ul>
      <div className="mt-6 flex gap-3">
        <Button variant="secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>{t('common:previous')}</Button>
        <Button disabled={query.data.next_offset === null} onClick={() => setOffset(query.data?.next_offset ?? offset)}>{t('common:next')}</Button>
      </div>
    </>}
  </section>;
}
