import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Link, useParams } from 'react-router';
import Alert from '../../components/common/Alert';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import Spinner from '../../components/common/Spinner';
import ProductForm from '../../components/products/ProductForm';
import ProductStatusBadge from '../../components/products/ProductStatusBadge';
import ProductImageManager from '../../components/products/ProductImageManager';
import { productErrorMessage } from '../../features/products/api';
import { useMyProduct, useProductMutation } from '../../features/products/hooks';
import { productSlugSchema } from '../../features/products/schemas';
import type { ProductAction } from '../../features/products/types';

export default function EditProductPage() {
  const { t } = useAppTranslation();
  const slug = useParams().slug ?? '';
  const query = useMyProduct(slug);
  const mutation = useProductMutation();
  if (!productSlugSchema.safeParse(slug).success) return <Alert>{t('products:unavailable')}</Alert>;
  if (query.isPending) return <Spinner label={t('products:loadingOwn')} />;
  if (query.isError || !query.data) return <Alert>{localizeMessage(productErrorMessage(query.error))} <button onClick={() => void query.refetch()}>{t('products:retry')}</button></Alert>;
  const product = query.data;
  async function act(action: ProductAction) {
    try { await mutation.mutateAsync({ action, slug }); } catch { /* Safe error state below. */ }
  }
  return <section className="mx-auto max-w-2xl">
    <Link className="text-red-700 underline" to="/seller/listings">{t('products:backToMine')}</Link>
    <div className="my-5 flex items-center justify-between gap-3"><h1 className="text-3xl font-black">{t('products:manage')}</h1><ProductStatusBadge status={product.status} /></div>
    {mutation.isError && <Alert>{localizeMessage(productErrorMessage(mutation.error))}</Alert>}
    <div className="mb-5 flex flex-wrap gap-3">
      {(product.status === 'DRAFT' || product.status === 'PAUSED') && <Button disabled={mutation.isPending} onClick={() => void act('publish')}>{t('products:publish')}</Button>}
      {product.status === 'PUBLISHED' && <Button disabled={mutation.isPending} onClick={() => void act('pause')}>{t('products:pause')}</Button>}
      {product.status !== 'ARCHIVED' && <Button variant="secondary" disabled={mutation.isPending} onClick={() => void act('archive')}>{t('products:archive')}</Button>}
      {product.status === 'PUBLISHED' && <Link className="p-3 text-red-700 underline" to={'/p/' + product.public_slug}>{t('products:publicPage')}</Link>}
    </div>
    <p className="mb-4 text-sm text-slate-600">{t('products:lifecycleCopy')}</p>
    <Card className="p-6"><ProductForm key={product.updated_at} product={product} /></Card>
    <ProductImageManager key={product.public_slug} product={product} />
  </section>;
}
