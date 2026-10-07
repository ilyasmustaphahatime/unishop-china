import { useQuery } from '@tanstack/react-query';
import { getCities } from './api';

export const cityKeys = { list: ['catalog', 'cities'] as const };
export function useCities() {
  return useQuery({ queryKey: cityKeys.list, queryFn: getCities, staleTime: 60_000, retry: 1 });
}
