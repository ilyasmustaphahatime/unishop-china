import { useEffect, useRef, useState } from 'react';
import { useImageIdentity, useOwnerImageBlob } from '../../features/productImages/hooks';
import { currentSessionVersion } from '../../services/apiClient';

export default function OwnerProductImage({ slug, imageRef, position }: { slug: string; imageRef: string; position: number }) {
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
  if (query.isError || failed) return <p role="status">Preview unavailable.</p>;
  if (!query.data || !enabled) return <p role="status">Loading image preview…</p>;
  return <img ref={element} className="aspect-square w-full rounded-lg object-contain" alt={'Your product image ' + (position + 1)}
    onError={() => setFailed(true)} />;
}
