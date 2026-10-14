import { formatNumber } from '../../i18n/formatters';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import { useEffect, useRef, useState } from 'react';
import { useImageIdentity, useOwnerImageBlob } from '../../features/productImages/hooks';
import { currentSessionVersion } from '../../services/apiClient';

export default function OwnerProductImage({ slug, imageRef, position }: { slug: string; imageRef: string; position: number }) {
  const { t } = useAppTranslation();
  const query = useOwnerImageBlob(slug, imageRef);
  const { id, version, enabled } = useImageIdentity();
  const element = useRef<HTMLImageElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const image = element.current;
    if (!image || !query.data || query.isError || failed || !enabled || version !== currentSessionVersion()) return;
    const url = URL.createObjectURL(query.data);
    image.src = url;
    return () => {
      image.removeAttribute('src');
      URL.revokeObjectURL(url);
    };
  }, [query.data, query.isError, failed, enabled, id, version, imageRef]);
  if (query.isError || failed) return <p role="status">{t('products:previewUnavailable')}</p>;
  if (!query.data || !enabled) return <p role="status">{t('products:loadingPreview')}</p>;
  return <img ref={element} className="aspect-square w-full rounded-lg object-contain" alt={t('products:ownerImageAlt', { number: formatNumber(position + 1) })}
    onError={() => setFailed(true)} />;
}
