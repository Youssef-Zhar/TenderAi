import axios from 'axios'

export const TOKEN_STORAGE_KEY = 'tenderai_access_token'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  headers: {
    Accept: 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem(TOKEN_STORAGE_KEY)

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail

    if (typeof detail === 'string') {
      return detail
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item: { msg?: string }) => item.msg || 'Invalid request')
        .join(', ')
    }

    if (!error.response) {
      return 'Cannot reach the TenderAI API. Check that the backend is running.'
    }
  }

  return 'An unexpected error occurred. Please try again.'
}

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (
      axios.isAxiosError(error) &&
      error.response?.status === 401 &&
      !error.config?.url?.includes('/auth/login')
    ) {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY)
      window.dispatchEvent(new Event('tenderai:unauthorized'))
    }

    return Promise.reject(error)
  },
)
