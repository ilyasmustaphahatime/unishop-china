import { useState } from 'react';
import { Link } from 'react-router';
import Alert from '../../components/common/Alert';
import Button from '../../components/common/Button';
import Spinner from '../../components/common/Spinner';
import ProductStatusBadge from '../../components/products/ProductStatusBadge';
import { useMyProducts } from '../../features/products/hooks';
import { productErrorMessage } from '../../features/products/api';

export default function SellerProductsPage() {
  const [offset, setOffset] = useState(0);
  const query = useMyProducts(offset);
  return <section>
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="text-3xl font-black">My listings</h1>
      <Link className="rounded-xl bg-red-600 px-4 py-3 font-semibold text-white" to="/sell/new">New listing</Link>
    </div>
    <p className="my-4 text-slate-600">Private drafts, published, paused, and archived listings. Active owners retain access even if seller eligibility changes.</p>
    {query.isPending && <Spinner label="Loading your listings" />}
    {query.isError && <Alert>{productErrorMessage(query.error)} <button onClick={() => void query.refetch()}>Retry listings</button></Alert>}
    {query.data && !query.isError && <>
      {!query.data.items.length && <p role="status">No listings on this page yet.</p>}
      <ul className="space-y-3">{query.data.items.map((p) => <li key={p.public_slug} className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link className="font-bold text-red-700 underline" to={'/seller/listings/' + p.public_slug + '/edit'}>{p.title}</Link>
          <ProductStatusBadge status={p.status} />
        </div>
        <p className="mt-2">{p.price} CNY · {p.city.name_en} · {p.category.name_en}</p>
        <p className="mt-1 text-sm text-slate-600">Condition: {p.condition.replace('_', ' ')}</p>
        <p className="text-sm text-slate-600">Updated: <time dateTime={p.updated_at}>{p.updated_at}</time></p>
        {(!p.city_active || !p.category_active) && <p className="text-sm text-amber-800">A catalog entry is retired; update it before publishing.</p>}
      </li>)}</ul>
      <div className="mt-6 flex gap-3">
        <Button variant="secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button>
        <Button disabled={query.data.next_offset === null} onClick={() => setOffset(query.data?.next_offset ?? offset)}>Next</Button>
      </div>
    </>}
  </section>;
}
