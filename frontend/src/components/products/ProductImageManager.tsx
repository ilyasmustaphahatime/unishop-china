import { useRef, useState } from 'react';
import Alert from '../common/Alert';
import Button from '../common/Button';
import OwnerProductImage from './OwnerProductImage';
import { useImageMutation, useMyProductImages } from '../../features/productImages/hooks';
import { IMAGE_LIMITS, validateUpload } from '../../features/productImages/schemas';
import { imageErrorMessage } from '../../features/productImages/api';
import type { ImageCommand } from '../../features/productImages/types';
import type { OwnProduct } from '../../features/products/types';

export default function ProductImageManager({ product }: { product: OwnProduct }) {
  const query = useMyProductImages(product.public_slug);
  const mutation = useImageMutation(product.public_slug);
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const busy = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const editable = product.status !== 'ARCHIVED';
  async function send(command: ImageCommand) {
    if (busy.current) return;
    busy.current = true;
    try {
      await mutation.mutateAsync(command);
      if (command.action === 'upload') {
        setFile(null);
        if (input.current) input.current.value = '';
      }
    } catch { /* Never render raw HTTP errors, filenames or storage paths. */ }
    finally { busy.current = false; }
  }
  const images = query.data ?? [];
  function move(index: number, delta: number) {
    const refs = images.map((image) => image.ref);
    [refs[index], refs[index + delta]] = [refs[index + delta], refs[index]];
    void send({ action: 'reorder', refs });
  }
  return <section className="mt-6 rounded-xl border border-slate-200 bg-white p-6" aria-label="Product images">
    <h2 className="text-xl font-bold">Product images</h2>
    <p className="my-2 text-sm text-slate-600">Up to 8 static JPEG, PNG or WebP images, 10 MiB each. First image is the cover. Metadata is removed before storage.</p>
    {query.isPending && <p role="status">Loading image metadata…</p>}
    {query.isError && <Alert>{imageErrorMessage(query.error)} <button onClick={() => void query.refetch()}>Retry image list</button></Alert>}
    {mutation.isError && <Alert>{imageErrorMessage(mutation.error)}</Alert>}
    {validation && <Alert>{validation}</Alert>}
    {product.status === 'ARCHIVED' && <p className="my-2 text-sm">Archived: images cannot be uploaded or reordered. You may still delete them.</p>}
    {query.isSuccess && !images.length && <p role="status">No images yet. Publishing without images remains allowed.</p>}
    {query.isSuccess && <ol className="my-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
      {images.map((image, index) => <li key={image.ref} className="rounded-lg border p-3">
        <OwnerProductImage slug={product.public_slug} imageRef={image.ref} position={image.position} />
        <p className="my-2 text-sm font-semibold">{index === 0 ? 'Cover image' : 'Image ' + (index + 1)}</p>
        <div className="flex flex-wrap gap-2">
          {editable && <><Button variant="secondary" disabled={mutation.isPending || index === 0} onClick={() => move(index, -1)}>Move left</Button>
            <Button variant="secondary" disabled={mutation.isPending || index === images.length - 1} onClick={() => move(index, 1)}>Move right</Button></>}
          <Button variant="secondary" disabled={mutation.isPending} onClick={() => void send({ action: 'delete', ref: image.ref })}>Delete image {index + 1}</Button>
        </div>
      </li>)}
    </ol>}
    {editable && <div className="mt-4 flex flex-col gap-3">
      <label htmlFor="product-image-file" className="font-semibold">Add image</label>
      <input ref={input} id="product-image-file" type="file" accept="image/jpeg,image/png,image/webp"
        disabled={mutation.isPending || !query.isSuccess || images.length >= IMAGE_LIMITS.count}
        onChange={(event) => {
          const selected = event.target.files?.[0] ?? null;
          const error = selected ? validateUpload(selected) : null;
          setValidation(error); setFile(error ? null : selected);
        }} />
      <Button disabled={!file || mutation.isPending || images.length >= IMAGE_LIMITS.count}
        onClick={() => { if (file) void send({ action: 'upload', file }); }}>
        {mutation.isPending ? 'Updating images…' : 'Upload image'}
      </Button>
    </div>}
  </section>;
}
