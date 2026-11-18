import { api } from '../lib/api'

export interface AuthUser {
  id: number
  email: string
  is_active: boolean
}

interface TokenResponse {
  access_token: string
  token_type: string
}

export interface AuthCredentials {
  email: string
  password: string
}

export const authService = {
  async login(credentials: AuthCredentials): Promise<TokenResponse> {
    const { data } = await api.post<TokenResponse>('/auth/login', credentials)
    return data
  },

  async register(credentials: AuthCredentials): Promise<AuthUser> {
    const { data } = await api.post<AuthUser>('/auth/register', credentials)
    return data
  },

  async me(): Promise<AuthUser> {
    const { data } = await api.get<AuthUser>('/auth/me')
    return data
  },
}
