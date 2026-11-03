import { useEffect, useRef, useState } from 'react'
import { authFetch, Invoice } from '../api/client'
import { Button } from './ui/button'

export function InvoicePdfPreview({ invoice, onClose }: { invoice: Invoice; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | undefined
    setUrl(null)
    setError('')
    const load = async () => {
      try {
        const response = await authFetch(`/invoices/${invoice.id}/pdf`, { signal: controller.signal })
        if (!response.ok) throw new Error('Unable to load this PDF. Please try again.')
        const blob = await response.blob()
        if (controller.signal.aborted) return
        if (!blob.type.includes('application/pdf')) throw new Error('The server did not return a PDF.')
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Unable to load PDF.')
      }
    }
    void load()
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [invoice.id, attempt])

  return (
    <dialog ref={dialog} onCancel={onClose} aria-labelledby="pdf-preview-title"
      className="m-auto h-[calc(100dvh-2rem)] max-h-none w-[calc(100vw-2rem)] max-w-6xl rounded-lg border bg-background p-0 text-foreground shadow-lg backdrop:bg-black/80">
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex shrink-0 flex-wrap items-center gap-3 border-b p-4">
          <div className="min-w-0 flex-1">
            <h2 id="pdf-preview-title" className="text-lg font-semibold">PDF preview</h2>
            <p className="truncate text-sm text-muted-foreground" title={invoice.filename}>{invoice.filename}</p>
          </div>
          {url && <a href={url} download={invoice.filename} className="text-sm font-medium text-blue-600 hover:underline">Download PDF</a>}
          <Button variant="outline" onClick={onClose} autoFocus>Close</Button>
        </header>
        {error ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
            <p role="alert">{error}</p>
            <Button variant="outline" onClick={() => setAttempt((value) => value + 1)}>Try again</Button>
          </div>
        ) : url ? (
          <>
            <iframe src={url} title={`PDF: ${invoice.filename}`} className="min-h-0 w-full flex-1 border-0" />
            <p className="shrink-0 px-4 py-2 text-xs text-muted-foreground">If your browser cannot display the PDF, use Download PDF.</p>
          </>
        ) : <p role="status" className="flex flex-1 items-center justify-center p-6">Loading PDF...</p>}
      </div>
    </dialog>
  )
}
