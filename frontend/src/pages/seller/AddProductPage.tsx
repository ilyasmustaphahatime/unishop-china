import { useAppTranslation } from '../../i18n/useAppTranslation';
import { Link } from 'react-router';
import Card from '../../components/common/Card';
import ProductForm from '../../components/products/ProductForm';

export default function AddProductPage() {
  const { t } = useAppTranslation();
  return <section className="mx-auto max-w-2xl">
    <h1 className="text-3xl font-black">{t('products:create')}</h1>
    <p className="my-4 text-slate-600">{t('products:createCopy')}</p>
    <Link className="text-red-700 underline" to="/seller/verification">{t('verification:sellerTitle')}</Link>
    <Card className="mt-5 p-6"><ProductForm /></Card>
  </section>;
}
