import { catalogName } from '../../i18n/formatters';
import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo, useRef } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';
import Alert from '../common/Alert';
import Button from '../common/Button';
import FormField from '../common/FormField';
import Input from '../common/Input';
import Select from '../common/Select';
import Textarea from '../common/Textarea';
import CitySelect from '../profiles/CitySelect';
import { useCategories } from '../../features/categories/hooks';
import { productErrorMessage } from '../../features/products/api';
import { useProductMutation } from '../../features/products/hooks';
import { productInputSchema } from '../../features/products/schemas';
import type { OwnProduct, ProductInput } from '../../features/products/types';
import { useAuthStore } from '../../stores/authStore';
import { requireCurrentSession } from '../../services/apiClient';

export default function ProductForm({ product }: { product?: OwnProduct }) {
  const { t } = useAppTranslation();
  const mutation = useProductMutation();
  const categories = useCategories();
  const navigate = useNavigate();
  const version = useAuthStore((s) => s.sessionVersion);
  const submitting = useRef(false);
  const original = useMemo<ProductInput>(() => product ? {
    title: product.title, description: product.description, price: product.price, condition: product.condition,
    city_slug: product.city.slug, category_slug: product.category.slug,
  } : { title: '', description: '', price: '', condition: 'good', city_slug: '', category_slug: '' }, [product]);
  const { register, handleSubmit, control, reset, formState: { errors } } = useForm<ProductInput>({
    resolver: zodResolver(productInputSchema), defaultValues: original,
  });
  useEffect(() => { reset(original); }, [original, reset]);
  const selectedCity = useWatch({ control, name: 'city_slug' });
  const selectedCategory = useWatch({ control, name: 'category_slug' });
  const options = categories.data?.flatMap((root) => [root, ...root.children]) ?? [];
  const historical = product && categories.isSuccess && !options.some((c) => c.slug === product.category.slug);
  const archived = product?.status === 'ARCHIVED';
  async function submit(input: ProductInput) {
    // React's pending render can lag two submit events during async validation.
    // Hold one synchronous guard until the first request settles.
    if (submitting.current) return;
    submitting.current = true;
    try {
      if (product) {
        const patch: Partial<ProductInput> = {};
        for (const field of ['title', 'description', 'price', 'city_slug', 'category_slug'] as const) {
          if (input[field] !== original[field]) patch[field] = input[field];
        }
        if (input.condition !== original.condition) patch.condition = input.condition;
        if (!Object.keys(patch).length) return;
        await mutation.mutateAsync({ action: 'update', slug: product.public_slug, input: patch });
        requireCurrentSession(version);
        navigate('/seller/listings', { replace: true });
      } else {
        const created = await mutation.mutateAsync({ action: 'create', input });
        requireCurrentSession(version);
        navigate('/seller/listings/' + created.public_slug + '/edit', { replace: true });
      }
    } catch { /* Safe mutation state is rendered below; never raw API payloads. */ }
    finally { submitting.current = false; }
  }
  return <form className="space-y-5" onSubmit={(event) => void handleSubmit(submit)(event)} noValidate>
    {mutation.isError && <Alert>{localizeMessage(productErrorMessage(mutation.error))}</Alert>}
    {archived && <p role="status">{t('products:readOnly')}</p>}
    <fieldset disabled={archived || mutation.isPending} className="space-y-5">
      <FormField id="product-title" label={t('products:title')} error={errors.title?.message}>
        <Input id="product-title" {...register('title')} aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? 'product-title-error' : undefined} />
      </FormField>
      <FormField id="product-description" label={t('products:description')} error={errors.description?.message} hint={t('products:descriptionHint')}>
        <Textarea id="product-description" rows={6} {...register('description')} aria-invalid={Boolean(errors.description)} aria-describedby={errors.description ? 'product-description-error' : 'product-description-hint'} />
      </FormField>
      <FormField id="product-price" label={t('products:price')} error={errors.price?.message} hint={t('products:priceHint')}>
        <Input id="product-price" dir="ltr" inputMode="decimal" type="text" {...register('price')} aria-invalid={Boolean(errors.price)} aria-describedby={errors.price ? 'product-price-error' : 'product-price-hint'} />
      </FormField>
      <FormField id="product-condition" label={t('products:condition')} error={errors.condition?.message}>
        <Select id="product-condition" {...register('condition')}>
          <option value="new">{t('products:new')}</option><option value="like_new">{t('products:likeNew')}</option>
          <option value="good">{t('products:good')}</option><option value="fair">{t('products:fair')}</option>
        </Select>
      </FormField>
      <FormField id="product-city" label={t('catalog:city')} error={errors.city_slug?.message}>
        <CitySelect id="product-city" registration={register('city_slug')} value={selectedCity}
          currentSlug={product?.city.slug} currentName={product ? catalogName(product.city) : undefined} />
      </FormField>
      <FormField id="product-category" label={t('catalog:category')} error={errors.category_slug?.message}>
        {categories.isError && <Alert>{t('catalog:loadCategoriesFailed')}<button type="button" onClick={() => void categories.refetch()}>{t('catalog:retryCategories')}</button></Alert>}
        {categories.isSuccess && !options.length && <p role="status">{t('catalog:noCategories')}</p>}
        {historical && <p role="status">{t('catalog:historicalCategoryCopy')}</p>}
        <Select id="product-category" {...register('category_slug')} value={selectedCategory}
          disabled={!categories.isSuccess || !options.length} aria-invalid={Boolean(errors.category_slug)}>
          <option value="">{categories.isPending ? t('catalog:loadingCategoriesOption') : t('catalog:chooseCategory')}</option>
          {historical && <option value={product.category.slug} disabled>{t('catalog:retiredCategory', { name: catalogName(product.category) })}</option>}
          {options.map((c) => <option key={c.slug} value={c.slug}>{c.parent_slug ? '— ' : ''}{catalogName(c)}</option>)}
        </Select>
      </FormField>
      {!archived && <Button type="submit" disabled={mutation.isPending || (!product && (!categories.isSuccess || !options.length))}>
        {mutation.isPending ? t('common:saving') : product ? t('products:saveChanges') : t('products:createDraft')}
      </Button>}
    </fieldset>
  </form>;
}
