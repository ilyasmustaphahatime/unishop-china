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
  const cities = useCities();
  const historical = cities.isSuccess && currentSlug && !cities.data.some((city) => city.slug === currentSlug);
  return <>
    {cities.isError && <Alert>Cities could not be loaded. <button type="button" onClick={() => void cities.refetch()}>Retry cities</button></Alert>}
    {cities.isSuccess && cities.data.length === 0 && <p role="status">No cities are currently available.</p>}
    {historical && <p role="status">Your saved city is no longer selectable. It remains on your profile; choose an active city to change it.</p>}
    <Select id={id} {...registration} value={value} disabled={!cities.isSuccess || cities.data.length === 0}>
      <option value="">{cities.isPending ? 'Loading cities…' : 'Choose your city'}</option>
      {historical && <option value={currentSlug} disabled>{currentName} (no longer available)</option>}
      {cities.data?.map((city) => <option key={city.slug} value={city.slug}>{city.name_en} · {city.name_zh}</option>)}
    </Select>
  </>;
}
