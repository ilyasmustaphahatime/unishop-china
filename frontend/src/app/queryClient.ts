import { QueryClient } from '@tanstack/react-query';
export const queryClient = new QueryClient();

export function clearPrivateQueryCache() {
  queryClient.removeQueries({
    predicate: (query) => query.meta?.private === true || query.queryKey[0] === 'auth',
  });
}
