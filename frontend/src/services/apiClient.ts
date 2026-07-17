import axios from 'axios';
import { tokenStorage } from './tokenStorage';
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15_000,
});
apiClient.interceptors.request.use((config) => { const token = tokenStorage.get(); if (token) config.headers.Authorization = `Bearer ${token}`; return config; });
apiClient.interceptors.response.use((r) => r, async (error) => { /* TODO: call refresh endpoint once implemented. */ return Promise.reject(error); });
