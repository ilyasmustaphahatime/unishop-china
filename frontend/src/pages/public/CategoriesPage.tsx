import { useCategories } from '../../features/categories/hooks';
import Alert from '../../components/common/Alert';
import Card from '../../components/common/Card';
import Spinner from '../../components/common/Spinner';

export default function CategoriesPage() {
  const categories = useCategories();
  if (categories.isPending) return <Spinner label="Loading categories" />;
  if (categories.isError) return <Alert>Categories could not be loaded. <button onClick={() => void categories.refetch()}>Retry categories</button></Alert>;
  return <section className="mx-auto max-w-3xl space-y-5 p-6">
    <h1 className="text-3xl font-bold">Categories</h1>
    <p>Community category directory. Product listings are not available yet.</p>
    {categories.data.length === 0 && <p role="status">No categories are currently available.</p>}
    <ul className="space-y-4">{categories.data.map((root) => <li key={root.slug}>
      <Card className="p-5">
        <h2 className="text-xl font-semibold">{root.name_en} · {root.name_zh}</h2>
        {root.description && <p>{root.description}</p>}
        <ul className="ml-5 list-disc">{root.children.map((child) => <li key={child.slug}>{child.name_en} · {child.name_zh}</li>)}</ul>
      </Card>
    </li>)}</ul>
  </section>;
}
