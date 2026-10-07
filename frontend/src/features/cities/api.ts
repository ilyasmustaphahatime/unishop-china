import { apiClient } from '../../services/apiClient';
import { cityListSchema } from './schemas';

export async function getCities() {
  const response = await apiClient.get('/cities');
  return cityListSchema.parse(response.data).items;
}
