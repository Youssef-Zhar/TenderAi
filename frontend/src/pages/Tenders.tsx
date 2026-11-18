import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { FilePlus2, LoaderCircle, RefreshCw, Trash2 } from 'lucide-react'
import { getApiErrorMessage } from '../lib/api'
import { tenderService, type Tender } from '../services/tenders'

function renderMarkdown(source: string): string {
  const escapeHtml = (value: string) =>
    value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;')

  const formatMath = (value: string) => {
    const readable = value
      .replace(/\\\\,/g, ' ')
      .replace(/\\[,;!]/g, ' ')
      .replace(/\\quad/g, '  ')
      .replace(/\\times/g, '×')
      .replace(/\\cdot/g, '·')
      .replace(/\\%/g, '%')
      .replace(/\\text\s*\{([^{}]*)\}/g, '$1')
      .replace(/\\mathrm\s*\{([^{}]*)\}/g, '$1')
      .replace(/\\left|\\right/g, '')
      .replace(/[{}]/g, '')
      .replace(/\\/g, '')
      .replace(/\s+/g, ' ')
      .trim()
    return '<span class="inline-block rounded bg-surface px-2 py-0.5 font-mono text-primary">' +
      escapeHtml(readable) + '</span>'
  }

  const inline = (value: string) => {
    const mathParts: string[] = []
    const withMath = value.replace(/\$\$([\s\S]+?)\$\$|\$([^$\n]+)\$/g, (_match, display: string | undefined, inlineMath: string | undefined) => {
      const token = '\u0000MATH' + mathParts.length + '\u0000'
      mathParts.push(formatMath(display ?? inlineMath ?? ''))
      return token
    })
    return escapeHtml(withMath)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\u0000MATH(\d+)\u0000/g, (_match, index: string) => mathParts[Number(index)] ?? '')
  }

  const normalized = source
    .replace(/\\([*_~])/g, '$1')
    .replace(/\r/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')

  const lines = normalized.split('\n')
  const isTableSeparator = (line: string) =>
    /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
  const cells = (line: string) =>
    line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
  const output: string[] = []

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim()
    if (!line) continue

    if (line.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = cells(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(cells(lines[index]))
        index += 1
      }
      index -= 1
      output.push(
        '<div class="my-4 overflow-x-auto rounded-lg border border-border"><table class="w-full border-collapse text-left text-sm">' +
        '<thead class="bg-surface"><tr>' + headers.map((cell) =>
          '<th class="border-b border-border px-3 py-2 font-semibold text-white">' + inline(cell) + '</th>'
        ).join('') + '</tr></thead><tbody>' +
        rows.map((row) => '<tr>' + headers.map((_header, cellIndex) =>
          '<td class="border-b border-border/60 px-3 py-2 align-top">' + inline(row[cellIndex] ?? '') + '</td>'
        ).join('') + '</tr>').join('') +
        '</tbody></table></div>'
      )
      continue
    }

    if (/^---+$/.test(line)) {
      output.push('<hr class="my-4 border-border" />')
      continue
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      const tag = heading[1].length <= 2 ? 'h3' : 'h4'
      output.push('<' + tag + ' class="mb-2 mt-4 font-semibold text-white">' +
        inline(heading[2]) + '</' + tag + '>')
      continue
    }
    if (/^[-*+]\s+/.test(line)) {
      output.push('<div class="my-1 flex gap-2 pl-2"><span aria-hidden="true">•</span><span>' +
        inline(line.replace(/^[-*+]\s+/, '')) + '</span></div>')
      continue
    }
    if (/^\*.+\*$/.test(line)) {
      output.push('<p class="my-2 italic text-muted">' + inline(line.replace(/^\*|\*$/g, '')) + '</p>')
      continue
    }
    output.push('<p class="my-2 leading-7">' + inline(line) + '</p>')
  }

  return output.join('')
}
export default function Tenders() {
  const [tenders, setTenders] = useState<Tender[]>([])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [budget, setBudget] = useState('')
  const [deadline, setDeadline] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const fetchTenders = useCallback(async () => {
    try {
      const records = await tenderService.list(0, 100)
      setTenders(records)
      setError('')
    } catch (loadError) {
      setError(getApiErrorMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [])

  const loadTenders = useCallback(async () => {
    setIsLoading(true)
    await fetchTenders()
  }, [fetchTenders])

  useEffect(() => {
    // This effect starts an external request; state updates happen when it settles.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTenders()
  }, [fetchTenders])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')
    setIsSaving(true)

    try {
      await tenderService.create({
        title: title.trim(),
        description: description.trim(),
        estimated_budget: budget.trim() ? Number(budget) : null,
        deadline: deadline || null,
      })
      setTitle('')
      setDescription('')
      setBudget('')
      setDeadline('')
      setNotice('Tender created successfully.')
      await loadTenders()
    } catch (saveError) {
      setError(getApiErrorMessage(saveError))
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDelete(tender: Tender) {
    if (!window.confirm(`Delete "${tender.title}"? This cannot be undone.`)) return

    setError('')
    setNotice('')
    try {
      await tenderService.remove(tender.id)
      setTenders((current) => current.filter((item) => item.id !== tender.id))
      setNotice('Tender deleted.')
    } catch (deleteError) {
      setError(getApiErrorMessage(deleteError))
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Tenders</h1>
          <p className="mt-2 text-sm text-muted">Manage tender records saved to your account.</p>
        </div>
        <button
          type="button"
          onClick={() => void loadTenders()}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm text-white hover:bg-surface-hover disabled:opacity-50"
        >
          <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && <p role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-4 text-sm text-red-300">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-success/30 bg-success/10 p-4 text-sm text-success">{notice}</p>}

      <section className="rounded-xl border border-border bg-surface p-6">
        <div className="mb-5 flex items-center gap-2">
          <FilePlus2 size={19} className="text-primary" />
          <h2 className="font-semibold text-white">Create a tender</h2>
        </div>
        <form onSubmit={handleCreate} className="grid gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <label htmlFor="tender-title" className="mb-2 block text-sm text-muted">Title</label>
            <input
              id="tender-title"
              required
              minLength={5}
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-white outline-none focus:border-primary"
              placeholder="Tender title"
            />
          </div>
          <div className="md:col-span-2">
            <label htmlFor="tender-description" className="mb-2 block text-sm text-muted">Description</label>
            <textarea
              id="tender-description"
              required
              minLength={20}
              rows={4}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="w-full resize-y rounded-lg border border-border bg-background px-4 py-3 text-sm text-white outline-none focus:border-primary"
              placeholder="Describe the procurement opportunity (at least 20 characters)"
            />
          </div>
          <div>
            <label htmlFor="tender-budget" className="mb-2 block text-sm text-muted">Estimated budget</label>
            <input
              id="tender-budget"
              type="number"
              min="0"
              step="any"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
              className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-white outline-none focus:border-primary"
              placeholder="Optional"
            />
          </div>
          <div>
            <label htmlFor="tender-deadline" className="mb-2 block text-sm text-muted">Deadline</label>
            <input
              id="tender-deadline"
              type="date"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
              className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-white outline-none focus:border-primary"
            />
          </div>
          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={isSaving}
              className="flex items-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-primary-hover disabled:opacity-50"
            >
              {isSaving && <LoaderCircle size={17} className="animate-spin" />}
              {isSaving ? 'Saving...' : 'Create tender'}
            </button>
          </div>
        </form>
      </section>

      <section className="overflow-hidden rounded-xl border border-border bg-surface">
        <div className="border-b border-border px-6 py-5">
          <h2 className="font-semibold text-white">Saved tenders</h2>
          <p className="mt-1 text-xs text-muted">Your account's tender records (maximum 100 shown)</p>
        </div>
        {isLoading ? (
          <p className="p-8 text-center text-sm text-muted">Loading tenders...</p>
        ) : tenders.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted">No tender records found.</p>
        ) : (
          <div className="divide-y divide-border">
            {tenders.map((tender) => (
              <article key={tender.id} className="flex flex-wrap items-start justify-between gap-4 px-6 py-5">
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium text-white">{tender.title}</h3>
                  <p className="mt-1 line-clamp-3 whitespace-pre-wrap break-words text-sm text-muted">{tender.description}</p>
                  {(tender.analysis_report || tender.description.length > 180) && (
                    <details className="mt-2 text-xs">
                      <summary className="w-fit cursor-pointer text-primary hover:text-primary-hover">
                        {tender.analysis_report ? 'View full AI analysis report' : 'View full description'}
                      </summary>
                      <div
                        className="mt-3 max-h-[32rem] overflow-y-auto break-words rounded-lg border border-border bg-background/50 p-4 text-sm text-muted"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(tender.analysis_report || tender.description) }}
                      />
                    </details>
                  )}
                  <p className="mt-2 text-xs text-muted">
                    Record #{tender.id}
                    {tender.estimated_budget !== null ? ` · Budget: ${tender.estimated_budget}` : ''}
                    {tender.deadline ? ` · Deadline: ${tender.deadline}` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleDelete(tender)}
                  aria-label={`Delete ${tender.title}`}
                  className="rounded-lg p-2 text-muted transition hover:bg-danger/10 hover:text-red-300"
                >
                  <Trash2 size={18} />
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
