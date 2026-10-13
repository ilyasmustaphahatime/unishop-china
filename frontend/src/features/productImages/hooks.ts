import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { currentSessionVersion, requireCurrentSession } from '../../services/apiClient';
import { productKeys } from '../products/hooks';
import { productSlugSchema } from '../products/schemas';
import { deleteProductImage, getMyProductImages, getOwnerImageBlob, reorderProductImages, uploadProductImage } from './api';
import { imageRefSchema } from './schemas';
import type { ImageCommand, OwnProductImage } from './types';

export const imageKeys = {
  mine: (id: string | undefined, version: number, slug: string) => ['product-images', 'mine', id, version, slug] as const,
  blob: (id: string | undefined, version: number, slug: string, ref: string) => [...imageKeys.mine(id, version, slug), 'blob', ref] as const,
};
export function useImageIdentity() {
  const id = useAuthStore((state) => state.user?.id);
  const version = useAuthStore((state) => state.sessionVersion);
  const authenticated = useAuthStore((state) => state.status === 'authenticated');
  return { id, version, enabled: authenticated && Boolean(id) };
}
export function useMyProductImages(slug: string) {
  const { id, version, enabled } = useImageIdentity();
  return useQuery({ queryKey: imageKeys.mine(id, version, slug),
    queryFn: () => { requireCurrentSession(version); return getMyProductImages(slug); },
    enabled: enabled && productSlugSchema.safeParse(slug).success,
    meta: { private: true }, staleTime: 0, gcTime: 0, retry: false });
}
export function useOwnerImageBlob(slug: string, ref: string) {
  const { id, version, enabled } = useImageIdentity();
  return useQuery({ queryKey: imageKeys.blob(id, version, slug, ref),
    queryFn: () => { requireCurrentSession(version); return getOwnerImageBlob(slug, ref); },
    enabled: enabled && productSlugSchema.safeParse(slug).success && imageRefSchema.safeParse(ref).success,
    meta: { private: true }, staleTime: 0, gcTime: 0, retry: false });
}
export function useImageMutation(slug: string) {
  const { id, version } = useImageIdentity();
  const client = useQueryClient();
  return useMutation<OwnProductImage | OwnProductImage[] | void, unknown, ImageCommand>({ mutationFn: (command: ImageCommand) => {
    requireCurrentSession(version);
    if (command.action === 'upload') return uploadProductImage(slug, command.file);
    if (command.action === 'reorder') return reorderProductImages(slug, command.refs);
    return deleteProductImage(slug, command.ref);
  }, onSuccess: (_result, command) => {
    if (version !== currentSessionVersion()) return;
    if (command.action === 'delete') client.removeQueries({ queryKey: imageKeys.blob(id, version, slug, command.ref) });
    void client.invalidateQueries({ queryKey: imageKeys.mine(id, version, slug), exact: true });
    // Media writes must not reset an unsaved product information form.
    void client.invalidateQueries({ queryKey: productKeys.mine(id, version),
      predicate: (query) => query.queryKey.includes('list') });
    client.removeQueries({ queryKey: productKeys.public(slug) });
  }, onError: () => {
    if (version === currentSessionVersion()) {
      void client.invalidateQueries({ queryKey: imageKeys.mine(id, version, slug), exact: true });
    }
  }, gcTime: 0, retry: false });
}
