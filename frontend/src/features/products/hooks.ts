import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { currentSessionVersion, requireCurrentSession } from '../../services/apiClient';
import { createProduct, getMyProduct, getMyProducts, getPublicProduct, transitionProduct, updateProduct } from './api';
import { productSlugSchema } from './schemas';
import type { ProductAction, ProductInput } from './types';

export const productKeys = {
  mine: (id: string | undefined, version: number) => ['products', 'mine', id, version] as const,
  own: (id: string | undefined, version: number, slug: string) => [...productKeys.mine(id, version), 'detail', slug] as const,
  public: (slug: string) => ['products', 'public', slug] as const,
};
function useIdentity() {
  const id = useAuthStore((s) => s.user?.id);
  const version = useAuthStore((s) => s.sessionVersion);
  const authenticated = useAuthStore((s) => s.status === 'authenticated');
  return { id, version, enabled: authenticated && Boolean(id) };
}
export function useMyProducts(offset = 0) {
  const { id, version, enabled } = useIdentity();
  return useQuery({ queryKey: [...productKeys.mine(id, version), 'list', offset],
    queryFn: () => { requireCurrentSession(version); return getMyProducts(offset); },
    enabled, meta: { private: true }, staleTime: 0, gcTime: 0, retry: false });
}
export function useMyProduct(slug: string) {
  const { id, version, enabled } = useIdentity();
  return useQuery({ queryKey: productKeys.own(id, version, slug),
    queryFn: () => { requireCurrentSession(version); return getMyProduct(slug); },
    enabled: enabled && productSlugSchema.safeParse(slug).success,
    meta: { private: true }, staleTime: 0, gcTime: 0, retry: false });
}
export function usePublicProduct(slug: string) {
  return useQuery({ queryKey: productKeys.public(slug), queryFn: () => getPublicProduct(slug),
    enabled: productSlugSchema.safeParse(slug).success, staleTime: 0, gcTime: 0, retry: false });
}
type Command = { action: 'create'; input: ProductInput }
  | { action: 'update'; slug: string; input: Partial<ProductInput> }
  | { action: ProductAction; slug: string };
export function useProductMutation() {
  const { id, version } = useIdentity();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (command: Command) => {
      requireCurrentSession(version);
      if (command.action === 'create') return createProduct(command.input);
      if (command.action === 'update') return updateProduct(command.slug, command.input);
      return transitionProduct(command.slug, command.action);
    },
    onSuccess: (product) => {
      if (version !== currentSessionVersion()) return;
      client.setQueryData(productKeys.own(id, version, product.public_slug), product);
      void client.invalidateQueries({ queryKey: productKeys.mine(id, version) });
      client.removeQueries({ queryKey: productKeys.public(product.public_slug) });
    },
    onError: (_error, command) => {
      if (version !== currentSessionVersion()) return;
      if ('slug' in command) void client.invalidateQueries({ queryKey: productKeys.own(id, version, command.slug) });
    },
    gcTime: 0,
  });
}
