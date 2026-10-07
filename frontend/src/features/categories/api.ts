import { apiClient } from '../../services/apiClient';
import { categoryListSchema } from './schemas';

export async function getCategories() {
  const response = await apiClient.get('/categories');
  return categoryListSchema.parse(response.data).items;
}
