import { catalogName } from '../../i18n/formatters';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { useCategories } from '../../features/categories/hooks';
import Alert from '../../components/common/Alert';
import Card from '../../components/common/Card';
import Spinner from '../../components/common/Spinner';

export default function CategoriesPage() {
  const { t } = useAppTranslation();
  const categories = useCategories();
  if (categories.isPending) return <Spinner label={t('catalog:loadingCategories')} />;
  if (categories.isError) return <Alert>{t('catalog:loadCategoriesFailed')}<button onClick={() => void categories.refetch()}>{t('catalog:retryCategories')}</button></Alert>;
  return <section className="mx-auto max-w-3xl space-y-5 p-6">
    <h1 className="text-3xl font-bold">{t('catalog:categories')}</h1>
    <p>{t('catalog:directoryCopy')}</p>
    {categories.data.length === 0 && <p role="status">{t('catalog:noCategories')}</p>}
    <ul className="space-y-4">{categories.data.map((root) => <li key={root.slug}>
      <Card className="p-5">
        <h2 className="text-xl font-semibold"><bdi>{catalogName(root)}</bdi></h2>
        {root.description && <p><bdi>{root.description}</bdi></p>}
        <ul className="ms-5 list-disc">{root.children.map((child) => <li key={child.slug}><bdi>{catalogName(child)}</bdi></li>)}</ul>
      </Card>
    </li>)}</ul>
  </section>;
}
