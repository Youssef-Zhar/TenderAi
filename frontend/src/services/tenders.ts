import { api } from '../lib/api'

export interface Tender {
  id: number
  title: string
  description: string
  analysis_report?: string | null
  estimated_budget: string | null
  currency: string | null
  deadline: string | null
  deadline_time: string | null
  deadline_text: string | null
}

export interface TenderCondition {
  id: number
  condition_type: string
  description: string
}

export interface TenderDocument {
  id: number
  name: string
  description: string | null
  is_mandatory: boolean
}

export interface TenderCriterion {
  id: number
  name: string
  description: string | null
  weight: number | null
}

export interface TenderEvidence {
  id: number
  field_name: string
  extracted_value: string | null
  page_number: number | null
  source_text: string | null
}

export interface TenderDetail extends Tender {
  conditions: TenderCondition[]
  documents: TenderDocument[]
  criteria: TenderCriterion[]
  evidence: TenderEvidence[]
}

export interface TenderInput {
  title: string
  description: string
  estimated_budget: string | null
  currency: string | null
  deadline: string | null
  deadline_time: string | null
}

export const tenderService = {
  async list(skip = 0, limit = 20): Promise<Tender[]> {
    const { data } = await api.get<Tender[]>('/api/v1/tenders/', {
      params: { skip, limit },
    })
    return data
  },

  async get(id: number): Promise<TenderDetail> {
    const { data } = await api.get<TenderDetail>(`/api/v1/tenders/${id}`)
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
