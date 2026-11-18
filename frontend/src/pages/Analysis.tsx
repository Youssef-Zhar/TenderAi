import { useState, type ChangeEvent, type FormEvent } from 'react'
import { AlertCircle, BrainCircuit, FileUp, LoaderCircle } from 'lucide-react'
import { analysisService, type AnalysisResponse } from '../services/analysis'
import { getApiErrorMessage } from '../lib/api'

const MAX_FILE_SIZE = 10 * 1024 * 1024

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
                  {result.filename} · {result.page_count} pages · {result.pages_with_text} pages with selectable text
                </p>
              </div>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                {result.analysis.status.replaceAll('_', ' ')}
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

          {structured && (
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
                  <dt className="text-xs text-muted">Verified evidence items</dt>
                  <dd className="mt-1 text-sm text-white">{structured.verified_evidence_count}</dd>
                </div>
              </dl>

              {structured.conditions.length > 0 && (
                <div className="mt-6">
                  <h3 className="font-semibold text-white">Conditions</h3>
                  <ul className="mt-3 space-y-3">
                    {structured.conditions.map((condition, index) => (
                      <li key={`${condition.condition_type}-${index}`} className="rounded-lg bg-background p-4">
                        <p className="text-xs font-semibold uppercase text-primary">{condition.condition_type}</p>
                        <p className="mt-1 text-sm text-white/90">{condition.description}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  )
}
