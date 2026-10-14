import { catalogName } from '../../i18n/formatters';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { useCities } from '../../features/cities/hooks';
import Alert from '../common/Alert';
import Select from '../common/Select';

export default function CitySelect({ id, registration, value, currentSlug, currentName }: {
  id: string;
  registration: UseFormRegisterReturn;
  value: string;
  currentSlug?: string | null;
  currentName?: string | null;
}) {
  const { t } = useAppTranslation();
  const cities = useCities();
  const historical = cities.isSuccess && currentSlug && !cities.data.some((city) => city.slug === currentSlug);
  return <>
    {cities.isError && <Alert>{t('catalog:loadCitiesFailed')}<button type="button" onClick={() => void cities.refetch()}>{t('catalog:retryCities')}</button></Alert>}
    {cities.isSuccess && cities.data.length === 0 && <p role="status">{t('catalog:noCities')}</p>}
    {historical && <p role="status">{t('catalog:historicalCityCopy')}</p>}
    <Select id={id} {...registration} value={value} disabled={!cities.isSuccess || cities.data.length === 0}>
      <option value="">{cities.isPending ? t('catalog:loadingCities') : t('catalog:chooseCity')}</option>
      {historical && <option value={currentSlug} disabled>{t('catalog:historicalCity', { name: currentName })}</option>}
      {cities.data?.map((city) => <option key={city.slug} value={city.slug}>{catalogName(city)}</option>)}
    </Select>
  </>;
}
