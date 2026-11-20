import { api } from '../lib/api'

export interface AnalysisResponse {
  filename: string
  page_count: number
  pages_with_text: number
  tender_id: number | null
  analysis: {
    status: string
    model: string
    report: string
    structured_data: {
      tender: {
        title: string | null
        reference: string | null
        contracting_authority: string | null
        estimated_budget: number | null
        currency: string | null
        deadline: string | null
        provisional_guarantee: string | null
        quantity: number | null
        processor: string | null
        ram_gb: number | null
        storage_gb: number | null
        screen_size_inches: number | null
        warranty_months: number | null
        accessories: string[]
      }
      conditions: Array<{ condition_type: string; description: string }>
      documents: Array<{ name: string; description: string | null; is_mandatory: boolean }>
      criteria: Array<{ name: string; description: string | null; weight: number | null }>
      evidence: Array<{
        field_name: string
        extracted_value: string | null
        page_number: number | null
        source_text: string | null
      }>
      extraction_conflicts: Array<{
        field_name: string
        first_value: string | number | null
        second_value: string | number | null
        first_chunk_index: number | null
        second_chunk_index: number | null
      }>
      verified_evidence_count: number
      rejected_evidence_count: number
      corrected_page_count: number
      ambiguous_evidence_count: number
    } | null
    metadata: {
      report_truncated: boolean
      structured_truncated: boolean
      structured_failed: boolean
      fallback_used: boolean
      rejected_evidence_count: number
      ambiguous_evidence_count: number
      extraction_conflict_count: number
      degradation_reasons: string[]
    }
  }
}

export const analysisService = {
  async analyzePdf(file: File): Promise<AnalysisResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const { data } = await api.post<AnalysisResponse>(
      '/api/v1/tenders/analyze-pdf',
      formData,
    )

    return data
  },
}
