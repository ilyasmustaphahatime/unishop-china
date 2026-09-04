import axios from 'axios';

export function profileErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return 'Something unexpected happened. Please try again.';
  if (!error.response) return 'Unable to reach UniShop China. Check your connection and try again.';
  if (error.response.status === 401) return 'Your session ended. Please sign in again.';
  if (error.response.status === 404) return 'This profile is not available.';
  if (error.response.status === 409) return 'Add a display name and city before finishing.';
  if (error.response.status === 422) return 'Check the profile details and try again.';
  if (error.response.status === 429) return 'Too many profile updates. Wait a moment and try again.';
  return 'The profile request could not be completed. Please try again.';
}
