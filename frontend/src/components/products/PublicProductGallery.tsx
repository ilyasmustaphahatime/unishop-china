import { formatNumber } from '../../i18n/formatters';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { useState } from 'react';
import { publicImageUrl } from '../../features/productImages/api';
import type { PublicProductImage } from '../../features/productImages/types';

function PublicImage({ slug, image }: { slug: string; image: PublicProductImage }) {
  const { t } = useAppTranslation();
  const [failed, setFailed] = useState(false);
  if (failed) return <div className="rounded-lg bg-slate-50 p-5"><p>{t('products:imageUnavailable')}</p>
    <button className="text-red-700 underline" onClick={() => setFailed(false)}>{t('products:retryImage')}</button></div>;
  return <img className="aspect-square w-full rounded-xl bg-slate-50 object-contain" loading="lazy"
    src={publicImageUrl(slug, image.ref)} alt={image.position === 0 ? t('products:coverAlt') : t('products:publicImageAlt', { number: formatNumber(image.position + 1) })}
    onError={() => setFailed(true)} />;
}
export default function PublicProductGallery({ slug, images }: { slug: string; images: PublicProductImage[] }) {
  const { t } = useAppTranslation();
  if (!images.length) return <p className="my-5 rounded-lg bg-slate-50 p-4 text-slate-500">{t('products:noPublicImages')}</p>;
  return <div className="my-5 grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label={t('products:gallery')}>
    {images.map((image) => <PublicImage key={image.ref} slug={slug} image={image} />)}
  </div>;
}
