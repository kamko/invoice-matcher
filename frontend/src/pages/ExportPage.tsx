import { useEffect, useState } from 'react'
import { Link, useSearch } from 'wouter'
import { useQueryClient } from '@tanstack/react-query'
import {
  authFetch, useDashboard, useInvoices, useCopyToGDrive, useSettings,
  useGDriveStatus, useFioVault, useAppConfig, useMailjetSenderStatus,
  useAccountantEmailPreview, showApiError, showSuccess,
} from '../api/client'
import { Card, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import { Checkbox } from '../components/ui/checkbox'
import { Download, Cloud, Loader2, Mail } from 'lucide-react'
import { getLegacyFioToken, unlockStoredSecret } from '../lib/crypto'

export function ExportPage() {
  const search = useSearch()
  const queryClient = useQueryClient()
  const { data: dashboard } = useDashboard()
  const { data: settings } = useSettings()
  const { data: gdrive } = useGDriveStatus()
  const { data: fioVault } = useFioVault()
  const { data: appConfig } = useAppConfig()
  const copy = useCopyToGDrive()
  const [month, setMonth] = useState(new URLSearchParams(search).get('month') || '')
  const [complete, setComplete] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)
  const [includeStatement, setIncludeStatement] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [emailBody, setEmailBody] = useState('')
  const { data: documents, isLoading, isError } = useInvoices(month || undefined, 'exportable')
  const { data: preview, isFetching: previewLoading, isError: previewError } = useAccountantEmailPreview(month || null, complete)
  const { data: sender } = useMailjetSenderStatus(settings?.mailjet_sender_email || '', Boolean(appConfig?.mailjet_enabled))
  const busy = copy.isPending || downloading
  const ready = documents?.invoices.filter((invoice) => !invoice.parent_invoice_id) || []
  const emailReady = Boolean(appConfig?.mailjet_enabled && sender?.active && settings?.company_name && settings?.accountant_email)
  const unresolved = preview?.unmatched_expenses || 0

  useEffect(() => {
    setEmailBody(preview?.body || '')
  }, [preview?.body, month, complete])
  useEffect(() => { setAcknowledged(false) }, [month, complete, unresolved])

  const refresh = () => {
    for (const key of ['invoices', 'dashboard', 'month-stats', 'accountant-email-preview']) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }

  const resolveFioToken = async () => {
    if (fioVault?.configured && fioVault.ciphertext && fioVault.nonce && fioVault.salt && fioVault.kdf && fioVault.kdf_params) {
      return unlockStoredSecret({ ciphertext: fioVault.ciphertext, nonce: fioVault.nonce, salt: fioVault.salt, kdf: fioVault.kdf, kdf_params: fioVault.kdf_params })
    }
    const legacy = getLegacyFioToken()?.trim()
    if (legacy) return legacy
    throw new Error('Configure your Fio token in Settings to include the monthly statement')
  }

  const handleCopy = async () => {
    if (!month || !settings?.accountant_folder_id || !preview) return
    try {
      const result = await copy.mutateAsync({
        yearMonth: month, folderId: settings.accountant_folder_id, markExported: true,
        includeMonthlyStatement: includeStatement,
        fioToken: includeStatement ? await resolveFioToken() : undefined,
        sendSummaryEmail: preview.will_send_email,
        emailBody: preview.will_send_email ? emailBody : undefined,
        completeMonth: complete, acknowledgeUnmatched: acknowledged,
      })
      const summary = `${result.copied} copied, ${result.skipped} already on Drive.`
      if (result.errors.length || result.email.status === 'failed') {
        showApiError(new Error([summary, ...result.errors, result.email.error].filter(Boolean).join(' ')), 'Handoff incomplete')
      } else {
        showSuccess(`${summary} ${result.email.status === 'sent' ? (complete ? 'Completion email sent.' : 'Notes emailed.') : 'No email needed.'}`)
      }
    } catch (error) { showApiError(error, 'Accountant handoff') }
  }

  const handleDownload = async () => {
    if (!month) return
    setDownloading(true)
    try {
      const response = await authFetch(`/export/${month}?mark_exported=false`)
      if (!response.ok) {
        const body = await response.json()
        throw new Error(body.detail || 'ZIP download failed')
      }
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `invoices_${month}.zip`
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
      refresh()
      showSuccess('ZIP downloaded. Mark documents as exported after handing them over manually.')
    } catch (error) { showApiError(error, 'Download ZIP') }
    finally { setDownloading(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Exportable</h1>
        <p className="mt-1 text-sm text-muted-foreground">Documents paired with payments and not yet handed over.</p>
      </div>
      <Card><CardContent className="space-y-5 p-4 sm:p-6">
        <div className="max-w-xs space-y-2">
          <Label htmlFor="export-month">Document month</Label>
          <Select id="export-month" value={month} disabled={busy} onChange={(event) => setMonth(event.target.value)} options={[
            { value: '', label: 'All months — select one to export' },
            ...(dashboard?.available_months.map((value) => ({ value, label: value })) || []),
          ]} />
        </div>
        <p className="text-sm text-muted-foreground">Grouped by document date. Only documents with a matched payment are included; cash and unpaired documents are excluded.</p>
        {isLoading ? <p role="status">Loading documents…</p> : isError ? <p role="alert" className="text-destructive">Could not load documents.</p> : ready.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Documents ready for accountant handoff</caption>
              <thead><tr className="border-b"><th className="p-2">Date</th><th className="p-2">Document</th><th className="p-2">Payment</th><th className="p-2">Note</th></tr></thead>
              <tbody>{ready.map((invoice) => <tr key={invoice.id} className="border-b">
                <td className="whitespace-nowrap p-2">{invoice.invoice_date}</td>
                <td className="max-w-sm break-words p-2"><a className="underline" href={`/api/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">{invoice.filename}</a><div className="text-muted-foreground">{invoice.vendor}</div></td>
                <td className="whitespace-nowrap p-2">{invoice.amount} {invoice.currency}<div className="text-muted-foreground">Matched</div></td>
                <td className="max-w-sm whitespace-pre-wrap break-words p-2">{invoice.comment || '—'}</td>
              </tr>)}</tbody>
            </table>
            <p className="mt-3 text-sm">{ready.length} documents ready</p>
          </div>
        ) : <p className="text-sm text-muted-foreground">No paired documents waiting for export. Match payments to documents in <Link className="underline" href="/transactions">Transactions</Link>, or select another month.</p>}
        {month && <>
          <div className="flex flex-wrap gap-2" aria-label="Handoff mode">
            <Button variant={complete ? 'outline' : 'default'} disabled={busy} aria-pressed={!complete} onClick={() => setComplete(false)}>Progressive export</Button>
            <Button variant={complete ? 'default' : 'outline'} disabled={busy} aria-pressed={complete} onClick={() => setComplete(true)}>Hand over the rest + confirm complete</Button>
          </div>
          <p className="text-sm">{complete ? 'Copies the remaining paired documents and confirms completion by email, including notes from all documents already handed over this month.' : 'Copies ready documents. No email is sent. All notes are summarized in the final email.'}</p>
          {complete && unresolved > 0 && <div className="space-y-3 rounded-md border p-4">
            <p role="alert" className="text-sm">{unresolved} expense payments in this payment month still have no document. <Link className="underline" href={`/transactions?month=${month}&status=unmatched&type=expense`}>Review payments</Link>.</p>
            <div className="flex items-start gap-2"><Checkbox id="ack-unmatched" checked={acknowledged} disabled={busy} onCheckedChange={(value) => setAcknowledged(value === true)} /><Label htmlFor="ack-unmatched" className="text-sm font-normal">I reviewed these payments and confirm the handoff is complete.</Label></div>
          </div>}
          <div className="flex items-center gap-2"><Checkbox id="include-statement" checked={includeStatement} disabled={busy} onCheckedChange={(value) => setIncludeStatement(value === true)} /><Label htmlFor="include-statement" className="text-sm font-normal">Include monthly Fio PDF statement on Drive</Label></div>
          {previewLoading ? <p role="status" className="text-sm">Preparing handoff…</p> : previewError ? <p role="alert" className="text-destructive">Could not prepare the handoff. Try again.</p> : preview && <>
            {preview.will_send_email && <section className="space-y-3 border-t pt-4" aria-labelledby="email-title">
              <h2 id="email-title" className="font-medium">Email preview</h2>
              <dl className="grid gap-2 text-sm sm:grid-cols-[4rem_1fr]">
                <dt>From</dt><dd className="break-all">{preview.sender_name} &lt;{preview.sender_email || 'not configured'}&gt;</dd>
                <dt>To</dt><dd className="break-all">{preview.to || 'not configured'}</dd>
                <dt>Bcc</dt><dd className="break-all">{preview.bcc}</dd>
                <dt>Subject</dt><dd>{preview.subject}</dd>
              </dl>
              <Label htmlFor="email-body">Message</Label>
              <textarea id="email-body" className="w-full rounded-md border bg-background p-3 text-sm" rows={7} maxLength={10000} value={emailBody} disabled={busy} onChange={(event) => setEmailBody(event.target.value)} />
              {!emailReady && <p className="text-sm text-destructive">Configure the company, accountant email and active Mailjet sender in Settings before sending this email.</p>}
            </section>}
          </>}
          {(!gdrive?.authenticated || !settings?.accountant_folder_id) && <p className="text-sm text-destructive">Connect Google Drive and select the accountant folder in Settings.</p>}
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleCopy} disabled={busy || isLoading || isError || previewLoading || previewError || !preview || !gdrive?.authenticated || !settings?.accountant_folder_id || (!complete && !ready.length) || (preview.will_send_email && (!emailReady || !emailBody.trim())) || (complete && unresolved > 0 && !acknowledged)}>
              {copy.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : complete ? <Mail className="mr-2 h-4 w-4" /> : <Cloud className="mr-2 h-4 w-4" />}
              {complete ? 'Hand over rest & confirm by email' : 'Copy to accountant'}
            </Button>
            <Button variant="outline" onClick={handleDownload} disabled={busy || isLoading || isError || !ready.length}><Download className="mr-2 h-4 w-4" />Download ZIP</Button>
          </div>
          <p className="text-sm text-muted-foreground">Drive handoffs mark successful files as exported automatically. ZIP download leaves their status unchanged; use Edit Invoice to mark a manual handoff.</p>
        </>}
      </CardContent></Card>
    </div>
  )
}
