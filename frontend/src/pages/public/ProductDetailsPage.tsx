import { conditionKeys } from '../../i18n/labels';
import { catalogName, formatCurrency } from '../../i18n/formatters';
import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Link, useParams } from 'react-router';
import Alert from '../../components/common/Alert';
import Card from '../../components/common/Card';
import Spinner from '../../components/common/Spinner';
import PublicProductGallery from '../../components/products/PublicProductGallery';
import { usePublicProduct } from '../../features/products/hooks';
import { productErrorMessage } from '../../features/products/api';
import { productSlugSchema } from '../../features/products/schemas';

export default function ProductDetailsPage() {
  const { t } = useAppTranslation();
  const slug = useParams().slug ?? '';
  const query = usePublicProduct(slug);
  if (!productSlugSchema.safeParse(slug).success) return <Alert>{t('products:unavailable')}</Alert>;
  if (query.isPending) return <Spinner label={t('products:loading')} />;
  if (query.isError || !query.data) return <Alert>{localizeMessage(productErrorMessage(query.error))} <button onClick={() => void query.refetch()}>{t('products:retry')}</button></Alert>;
  const p = query.data;
  return <article className="mx-auto max-w-3xl">
    <Card className="p-6 sm:p-8">
      <p className="text-sm font-semibold text-slate-500"><bdi>{catalogName(p.city)}</bdi> · <bdi>{catalogName(p.category)}</bdi></p>
      <h1 dir="auto" className="mt-3 break-words text-3xl font-black"><bdi>{p.title}</bdi></h1>
      <PublicProductGallery slug={p.public_slug} images={p.images} />
      <p className="mt-4 text-2xl font-bold text-red-700"><bdi>{formatCurrency(p.price)}</bdi></p>
      <p className="mt-2 text-slate-600">{t('products:conditionLine', { condition: t(conditionKeys[p.condition]) })}</p>
      <p dir="auto" className="mt-6 whitespace-pre-wrap break-words leading-7">{p.description}</p>
      <div className="mt-8 border-t border-slate-200 pt-5">
        <Link className="font-bold text-red-700 underline" to={'/u/' + p.seller.public_handle}><bdi>{p.seller.display_name}</bdi></Link>
        <span className="ms-3 rounded-full bg-green-50 px-3 py-1 text-sm text-green-800">{t('products:verifiedSeller')}</span>
      </div>
    </Card>
  </article>;
}
