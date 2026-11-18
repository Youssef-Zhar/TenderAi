import { api } from '../lib/api'

export interface Tender {
  id: number
  title: string
  description: string
  estimated_budget: number | null
  deadline: string | null
}

export interface TenderInput {
  title: string
  description: string
  estimated_budget: number | null
  deadline: string | null
}

export const tenderService = {
  async list(skip = 0, limit = 20): Promise<Tender[]> {
    const { data } = await api.get<Tender[]>('/api/v1/tenders/', {
      params: { skip, limit },
    })
    return data
  },

  async get(id: number): Promise<Tender> {
    const { data } = await api.get<Tender>(`/api/v1/tenders/${id}`)
    return data
  },

  async create(payload: TenderInput): Promise<Tender> {
    const { data } = await api.post<Tender>('/api/v1/tenders/', payload)
    return data
  },

  async update(id: number, payload: TenderInput): Promise<Tender> {
    const { data } = await api.put<Tender>(`/api/v1/tenders/${id}`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/api/v1/tenders/${id}`)
  },
}
