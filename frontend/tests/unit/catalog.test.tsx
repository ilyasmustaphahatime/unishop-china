import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { useForm, useWatch } from 'react-hook-form';
import { apiClient, clearAuthenticatedSession } from '../../src/services/apiClient';
import { queryClient } from '../../src/app/queryClient';
import { cityKeys } from '../../src/features/cities/hooks';
import { getCities } from '../../src/features/cities/api';
import { getCategories } from '../../src/features/categories/api';
import { cityListSchema } from '../../src/features/cities/schemas';
import { categoryListSchema } from '../../src/features/categories/schemas';
import { catalogSlugSchema } from '../../src/features/catalog/slugs';
import CitySelect from '../../src/components/profiles/CitySelect';
import CategoriesPage from '../../src/pages/public/CategoriesPage';
import ProfileForm from '../../src/components/profiles/ProfileForm';
import { useAuthStore } from '../../src/stores/authStore';

const city = { slug: 'fuzhou', name_en: 'Fuzhou', name_zh: '福州', province_en: 'Fujian', province_zh: '福建', country_code: 'CN' };
const child = { slug: 'test-phones', name_en: 'Phones', name_zh: '手机', description: null, parent_slug: 'test-electronics' };
const root = { slug: 'test-electronics', name_en: 'Electronics', name_zh: '电子', description: null, parent_slug: null, children: [child] };

function wrap(element: React.ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>);
}

function Selector({ historical = false }: { historical?: boolean }) {
  const { register, control } = useForm({ defaultValues: { city: historical ? 'retired-city' : '' } });
  const value = useWatch({ control, name: 'city' });
  return <><label htmlFor="city">City</label><CitySelect id="city" registration={register('city')} value={value}
    currentSlug={historical ? 'retired-city' : null} currentName="Historical City" /></>;
}

afterEach(() => {
  vi.restoreAllMocks();
  queryClient.clear();
  useAuthStore.getState().setBootstrapping();
});

describe('strict public catalog contracts', () => {
  it('loads dynamic city/category lists through their public APIs', async () => {
    const get = vi.spyOn(apiClient, 'get').mockImplementation(async (path) => ({ data: { items: path === '/cities' ? [city] : [root] } }));
    expect(await getCities()).toEqual([city]);
    expect(await getCategories()).toEqual([root]);
    expect(get.mock.calls.map(([path]) => path)).toEqual(['/cities', '/categories']);
  });

  it.each(['id', 'city_id', 'created_by', 'actor_id', 'created_at', 'storage_key'])('rejects leaked public field %s', (field) => {
    expect(cityListSchema.safeParse({ items: [{ ...city, [field]: 'private' }] }).success).toBe(false);
    expect(categoryListSchema.safeParse({ items: [{ ...root, [field]: 'private' }] }).success).toBe(false);
  });

  it.each(['../admin', 'UPPER', '青岛', 'admin', '%2Fadmin', 'with space', '9', 'a'.repeat(64)])('rejects unsafe slug %s', (slug) => {
    expect(catalogSlugSchema.safeParse(slug).success).toBe(false);
  });

  it('rejects a third level, duplicate slugs and inconsistent parent references', () => {
    expect(categoryListSchema.safeParse({ items: [{ ...root, children: [{ ...child, children: [] }] }] }).success).toBe(false);
    expect(categoryListSchema.safeParse({ items: [root, root] }).success).toBe(false);
    expect(categoryListSchema.safeParse({ items: [{ ...root, children: [{ ...child, parent_slug: 'another-root' }] }] }).success).toBe(false);
  });
});

describe('dynamic city controls', () => {
  it('renders loading while the API request is pending', () => {
    vi.spyOn(apiClient, 'get').mockReturnValue(new Promise(() => undefined));
    wrap(<Selector />);
    expect(screen.getByLabelText('City')).toBeDisabled();
    expect(screen.getByText('Loading cities…')).toBeInTheDocument();
  });

  it('renders safe errors without raw backend details', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('raw private SQL'));
    wrap(<Selector />);
    expect(await screen.findByRole('alert', {}, { timeout: 4000 })).toHaveTextContent('Cities could not be loaded');
    expect(screen.queryByText(/raw private SQL/)).toBeNull();
  });

  it('renders empty data without inventing a hardcoded fallback', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [] } });
    wrap(<Selector />);
    expect(await screen.findByRole('status')).toHaveTextContent('No cities are currently available');
    expect(screen.getByLabelText('City')).toBeDisabled();
    expect(screen.queryByText('Qingdao')).toBeNull();
  });

  it('selects a newly managed city by public slug only', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [city] } });
    wrap(<Selector />);
    await screen.findByRole('option', { name: 'Fuzhou · 福州' });
    await userEvent.setup().selectOptions(screen.getByLabelText('City'), 'fuzhou');
    expect(screen.getByLabelText('City')).toHaveValue('fuzhou');
    expect(document.querySelector('[href*="city_id"]')).toBeNull();
  });

  it('preserves a retired historical selection without making it selectable', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [city] } });
    wrap(<Selector historical />);
    expect(await screen.findByRole('status')).toHaveTextContent('It remains on your profile');
    expect(screen.getByRole('option', { name: 'Historical City (no longer available)' })).toBeDisabled();
    expect(screen.getByLabelText('City')).toHaveValue('retired-city');
  });

  it('does not reassign an unchanged retired city while editing a profile', async () => {
    const profile = { publicHandle: 'user-test123', displayName: 'Test User', bio: '', city: 'Retired City',
      citySlug: 'retired-city', cityActive: false, onboardingCompleted: true, memberSince: '2026-01-01',
      createdAt: '2026-01-01', updatedAt: '2026-01-01', emailVerified: true, phoneVerified: true };
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [city] } });
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: {
      public_handle: profile.publicHandle, display_name: profile.displayName, bio: '', city: profile.city,
      city_slug: profile.citySlug, city_active: false, onboarding_completed: true, member_since: profile.memberSince,
      created_at: profile.createdAt, updated_at: profile.updatedAt, email_verified: true, phone_verified: true,
    } });
    wrap(<ProfileForm profile={profile} />);
    await screen.findByRole('status');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Save profile' }));
    expect(patch).toHaveBeenCalledWith('/profile/me', { display_name: 'Test User', bio: null });
  });
});

describe('read-only category directory and cache boundaries', () => {
  it('renders two levels as inert text without any product features', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { items: [{ ...root, name_en: '<script>not executable</script>' }] } });
    wrap(<CategoriesPage />);
    expect(await screen.findByText('Phones · 手机')).toBeInTheDocument();
    expect(screen.getByText(/not executable/)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.queryByRole('link', { name: /product/i })).toBeNull();
  });

  it('retains only public catalog cache when private session data is cleared', async () => {
    queryClient.setQueryData(cityKeys.list, [city]);
    await queryClient.fetchQuery({ queryKey: ['private', 'admin'], queryFn: async () => ({ secret: 'private fixture' }), meta: { private: true } });
    clearAuthenticatedSession();
    expect(queryClient.getQueryData(cityKeys.list)).toEqual([city]);
    expect(queryClient.getQueryData(['private', 'admin'])).toBeUndefined();
  });
});
