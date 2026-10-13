import { Link, useParams } from 'react-router';
import Alert from '../../components/common/Alert';
import Card from '../../components/common/Card';
import Spinner from '../../components/common/Spinner';
import PublicProductGallery from '../../components/products/PublicProductGallery';
import { usePublicProduct } from '../../features/products/hooks';
import { productErrorMessage } from '../../features/products/api';
import { productSlugSchema } from '../../features/products/schemas';

export default function ProductDetailsPage() {
  const slug = useParams().slug ?? '';
  const query = usePublicProduct(slug);
  if (!productSlugSchema.safeParse(slug).success) return <Alert>This listing is not available.</Alert>;
  if (query.isPending) return <Spinner label="Loading listing" />;
  if (query.isError || !query.data) return <Alert>{productErrorMessage(query.error)} <button onClick={() => void query.refetch()}>Retry listing</button></Alert>;
  const p = query.data;
  return <article className="mx-auto max-w-3xl">
    <Card className="p-6 sm:p-8">
      <p className="text-sm font-semibold text-slate-500">{p.city.name_en} · {p.category.name_en}</p>
      <h1 className="mt-3 break-words text-3xl font-black">{p.title}</h1>
      <PublicProductGallery slug={p.public_slug} images={p.images} />
      <p className="mt-4 text-2xl font-bold text-red-700">{p.price} CNY</p>
      <p className="mt-2 text-slate-600">Condition: {p.condition.replace('_', ' ')}</p>
      <p className="mt-6 whitespace-pre-wrap break-words leading-7">{p.description}</p>
      <div className="mt-8 border-t border-slate-200 pt-5">
        <Link className="font-bold text-red-700 underline" to={'/u/' + p.seller.public_handle}>{p.seller.display_name}</Link>
        <span className="ml-3 rounded-full bg-green-50 px-3 py-1 text-sm text-green-800">Verified seller</span>
      </div>
    </Card>
  </article>;
}
