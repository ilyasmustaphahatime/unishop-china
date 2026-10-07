import { useQuery } from '@tanstack/react-query';
import { getCategories } from './api';

export const categoryKeys = { list: ['catalog', 'categories'] as const };
export function useCategories() {
  return useQuery({ queryKey: categoryKeys.list, queryFn: getCategories, staleTime: 60_000, retry: 1 });
}
