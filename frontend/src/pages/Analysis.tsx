import { useState, type ChangeEvent, type FormEvent } from 'react'
import { AlertCircle, BrainCircuit, FileUp, LoaderCircle } from 'lucide-react'
import { analysisService, type AnalysisResponse } from '../services/analysis'
import { getApiErrorMessage } from '../lib/api'

const MAX_FILE_SIZE = 10 * 1024 * 1024

function humanize(value: string): string {
  return value.replaceAll('_', ' ')
}

export default function Analysis() {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] || null
    setResult(null)
    setError('')

    if (!selected) {
      setFile(null)
      return
    }

    if (!selected.name.toLowerCase().endsWith('.pdf')) {
      setFile(null)
      setError('Please select a PDF file.')
      return
    }

    if (selected.size > MAX_FILE_SIZE) {
      setFile(null)
      setError('The PDF must not exceed 10 MB.')
      return
    }

    setFile(selected)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file) return

    setError('')
    setResult(null)
    setIsSubmitting(true)

    try {
      const response = await analysisService.analyzePdf(file)
      setResult(response)
    } catch (submitError) {
      setError(getApiErrorMessage(submitError))
    } finally {
      setIsSubmitting(false)
    }
  }

  const structured = result?.analysis.structured_data
  const metadata = result?.analysis.metadata

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">AI PDF Analysis</h1>
        <p className="mt-2 text-sm text-muted">
          Upload a tender dossier and review the AI-generated report and extracted details.
        </p>
      </div>

      <section className="rounded-xl border border-border bg-surface p-6">
        <form onSubmit={handleSubmit} className="space-y-5">
          <label
            htmlFor="tender-pdf"
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-border bg-background px-6 py-10 text-center transition hover:border-primary"
          >
            <FileUp size={34} className="text-primary" />
            <span className="mt-3 font-semibold text-white">
              {file ? file.name : 'Choose a tender PDF'}
            </span>
            <span className="mt-2 text-xs text-muted">
              PDF only · Maximum file size 10 MB
            </span>
            <input
              id="tender-pdf"
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleFileChange}
              className="sr-only"
            />
          </label>

          {file && (
            <p className="text-xs text-muted">
              {(file.size / 1024 / 1024).toFixed(2)} MB selected
            </p>
          )}

          {error && (
            <div role="alert" className="flex gap-2 rounded-lg border border-danger/30 bg-danger/10 p-4 text-sm text-red-300">
              <AlertCircle size={18} className="shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={!file || isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
          >
            {isSubmitting ? <LoaderCircle size={18} className="animate-spin" /> : <BrainCircuit size={18} />}
            {isSubmitting ? 'Analysing PDF...' : 'Analyse tender'}
          </button>
        </form>
      </section>

      {result && (
        <div className="space-y-6">
          <section className="rounded-xl border border-border bg-surface p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Analysis result</h2>
                <p className="mt-1 text-xs text-muted">
                  {result.filename} · {result.page_count} pages · {result.pages_with_text} pages with extracted text
                </p>
                <p className="mt-1 text-xs text-muted">Model: {result.analysis.model}</p>
              </div>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                {humanize(result.analysis.status)}
              </span>
            </div>
            {result.tender_id !== null && (
              <p className="mt-3 text-xs text-success">
                Saved to your tenders as record #{result.tender_id}
              </p>
            )}
            <div className="mt-6 whitespace-pre-wrap text-sm leading-7 text-white/90">
              {result.analysis.report}
            </div>
          </section>

          {metadata && (
            metadata.ocr_pages.length > 0 ||
            metadata.ocr_failed_pages.length > 0 ||
            metadata.ocr_skipped_pages.length > 0
          ) && (
            <section className="rounded-xl border border-border bg-surface p-5">
              <h2 className="font-semibold text-white">OCR processing</h2>
              {metadata.ocr_pages.length > 0 && (
                <p className="mt-2 text-sm text-success">
                  Text recovered from pages: {metadata.ocr_pages.join(', ')}.
                </p>
              )}
              {metadata.ocr_failed_pages.length > 0 && (
                <p className="mt-2 text-sm text-amber-200">
                  OCR failed on pages: {metadata.ocr_failed_pages.join(', ')}. Check Tesseract and the configured language data.
                </p>
              )}
              {metadata.ocr_skipped_pages.length > 0 && (
                <p className="mt-2 text-sm text-amber-200">
                  OCR was skipped on pages: {metadata.ocr_skipped_pages.join(', ')} because the per-upload OCR page limit was reached.
                </p>
              )}
            </section>
          )}

          {metadata && metadata.degradation_reasons.length > 0 && (
            <section
              role="status"
              className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-6"
            >
              <div className="flex items-start gap-3">
                <AlertCircle size={19} className="mt-0.5 shrink-0 text-amber-300" />
                <div className="min-w-0">
                  <h2 className="font-semibold text-amber-200">Analysis limitations</h2>
                  <p className="mt-1 text-sm leading-6 text-white/80">
                    The report was generated, but some extraction steps were incomplete.
                    Review these limitations against the original PDF before relying on the results.
                  </p>
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-white/80">
                    {metadata.degradation_reasons.map((reason, index) => (
                      <li key={`${reason}-${index}`}>{humanize(reason)}</li>
                    ))}
                  </ul>
                  {metadata.pages_without_text.length > 0 && (
                    <p className="mt-3 text-sm text-amber-200">
                      Pages without readable text after OCR: {metadata.pages_without_text.join(', ')}.
                      Their contents were not included in the AI analysis.
                    </p>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted">
                    {metadata.report_truncated && <span className="rounded bg-background px-2 py-1">Report evidence incomplete</span>}
                    {metadata.structured_truncated && <span className="rounded bg-background px-2 py-1">Structured extraction truncated</span>}
                    {metadata.structured_failed && <span className="rounded bg-background px-2 py-1">Structured extraction failed</span>}
                    {metadata.fallback_used && <span className="rounded bg-background px-2 py-1">Fallback extraction used</span>}
                  </div>
                </div>
              </div>
            </section>
          )}

          {structured && (
            <>
              <section className="rounded-xl border border-border bg-surface p-6">
                <h2 className="text-lg font-semibold text-white">Extracted tender details</h2>
                <dl className="mt-5 grid gap-4 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs text-muted">Title</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.title || 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Reference</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.reference || 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Contracting authority</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.contracting_authority || 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Estimated budget</dt>
                    <dd className="mt-1 text-sm text-white">
                      {structured.tender.estimated_budget ?? 'Not identified'} {structured.tender.currency || ''}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Submission deadline</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.deadline || 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Provisional guarantee</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.provisional_guarantee || 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Quantity</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.quantity ?? 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Processor</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.processor || 'Not identified'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">RAM</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.ram_gb === null ? 'Not identified' : `${structured.tender.ram_gb} GB`}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Storage</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.storage_gb === null ? 'Not identified' : `${structured.tender.storage_gb} GB`}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Screen size</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.screen_size_inches === null ? 'Not identified' : `${structured.tender.screen_size_inches} inches`}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Warranty</dt>
                    <dd className="mt-1 text-sm text-white">{structured.tender.warranty_months === null ? 'Not identified' : `${structured.tender.warranty_months} months`}</dd>
                  </div>
                </dl>

                {structured.tender.accessories.length > 0 && (
                  <div className="mt-6">
                    <h3 className="font-semibold text-white">Accessories</h3>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-white/80">
                      {structured.tender.accessories.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                    </ul>
                  </div>
                )}

                <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    ['Verified evidence', structured.verified_evidence_count],
                    ['Rejected evidence', structured.rejected_evidence_count],
                    ['Ambiguous evidence', structured.ambiguous_evidence_count],
                    ['Corrected evidence page references', structured.corrected_page_count],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg bg-background p-3">
                      <p className="text-xs text-muted">{label}</p>
                      <p className="mt-1 text-xl font-semibold text-white">{value}</p>
                    </div>
                  ))}
                </div>
              </section>

              {structured.conditions.length > 0 && (
                <section className="rounded-xl border border-border bg-surface p-6">
                  <h2 className="text-lg font-semibold text-white">Conditions</h2>
                  <ul className="mt-3 space-y-3">
                    {structured.conditions.map((condition, index) => (
                      <li key={`${condition.condition_type}-${index}`} className="rounded-lg bg-background p-4">
                        <p className="text-xs font-semibold uppercase text-primary">{condition.condition_type}</p>
                        <p className="mt-1 text-sm text-white/90">{condition.description}</p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {structured.documents.length > 0 && (
                <section className="rounded-xl border border-border bg-surface p-6">
                  <h2 className="text-lg font-semibold text-white">Required documents</h2>
                  <ul className="mt-3 space-y-3">
                    {structured.documents.map((document, index) => (
                      <li key={`${document.name}-${index}`} className="rounded-lg bg-background p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-white">{document.name}</p>
                          <span className="rounded bg-surface px-2 py-1 text-xs text-muted">
                            {document.is_mandatory ? 'Mandatory' : 'Optional'}
                          </span>
                        </div>
                        {document.description && <p className="mt-1 text-sm text-white/80">{document.description}</p>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {structured.criteria.length > 0 && (
                <section className="rounded-xl border border-border bg-surface p-6">
                  <h2 className="text-lg font-semibold text-white">Evaluation criteria</h2>
                  <ul className="mt-3 space-y-3">
                    {structured.criteria.map((criterion, index) => (
                      <li key={`${criterion.name}-${index}`} className="rounded-lg bg-background p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-white">{criterion.name}</p>
                          {criterion.weight !== null && <span className="text-xs font-semibold text-primary">Weight / score: {criterion.weight}</span>}
                        </div>
                        {criterion.description && <p className="mt-1 text-sm text-white/80">{criterion.description}</p>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {structured.extraction_conflicts.length > 0 && (
                <section className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-6">
                  <h2 className="text-lg font-semibold text-amber-200">Conflicting extracted values</h2>
                  <p className="mt-1 text-sm text-white/70">These are extraction conflicts between document sections. Verify both values in the source PDF.</p>
                  <div className="mt-4 space-y-3">
                    {structured.extraction_conflicts.map((conflict, index) => (
                      <div key={`${conflict.field_name}-${index}`} className="rounded-lg bg-background p-4">
                        <p className="text-xs font-semibold uppercase text-muted">{humanize(conflict.field_name)}</p>
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          <p className="text-sm text-white">First: {conflict.first_value ?? 'Not identified'} <span className="text-xs text-muted">(section {conflict.first_chunk_index ?? 'unknown'})</span></p>
                          <p className="text-sm text-white">Second: {conflict.second_value ?? 'Not identified'} <span className="text-xs text-muted">(section {conflict.second_chunk_index ?? 'unknown'})</span></p>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {structured.evidence.length > 0 && (
                <section className="rounded-xl border border-border bg-surface p-6">
                  <h2 className="text-lg font-semibold text-white">Source evidence</h2>
                  <ul className="mt-3 space-y-3">
                    {structured.evidence.map((item, index) => (
                      <li key={`${item.field_name}-${index}`} className="rounded-lg bg-background p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-xs font-semibold uppercase text-primary">{humanize(item.field_name)}</p>
                          <span className="text-xs text-muted">{item.page_number === null ? 'Page not identified' : `Page ${item.page_number}`}</span>
                        </div>
                        {item.extracted_value && <p className="mt-1 text-sm font-medium text-white">{item.extracted_value}</p>}
                        {item.source_text && <blockquote className="mt-2 border-l-2 border-primary/50 pl-3 text-sm italic leading-6 text-white/70">{item.source_text}</blockquote>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}

          {metadata && (
            <p className="text-xs text-muted">
              Evidence checks: {metadata.rejected_evidence_count} rejected · {metadata.ambiguous_evidence_count} ambiguous · {metadata.extraction_conflict_count} extraction conflicts
            </p>
          )}
        </div>
      )}
    </div>
  )
}
