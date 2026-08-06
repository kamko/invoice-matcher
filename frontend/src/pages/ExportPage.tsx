import { useState } from 'react'
import { useDashboard, useMonthStats, useCopyToGDrive, useSettings, useGDriveStatus, useFioVault, useAppConfig, useMailjetSenderStatus, showApiError, showSuccess } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import { Checkbox } from '../components/ui/checkbox'
import { Download, FileText, CheckCircle, Cloud, Loader2, Mail } from 'lucide-react'
import { getLegacyFioToken, unlockStoredSecret } from '../lib/crypto'

export function ExportPage() {
  const { data: dashboard } = useDashboard()
  const { data: settings } = useSettings()
  const { data: gdriveStatus } = useGDriveStatus()
  const { data: fioVault } = useFioVault()
  const { data: appConfig } = useAppConfig()
  const copyToGDrive = useCopyToGDrive()
  const [selectedMonth, setSelectedMonth] = useState('')
  const [markExported, setMarkExported] = useState(false)
  const [includeMonthlyStatement, setIncludeMonthlyStatement] = useState(false)
  const [isCopying, setIsCopying] = useState(false)

  const { data: stats, isLoading: statsLoading } = useMonthStats(selectedMonth || null)

  const accountantFolderId = settings?.accountant_folder_id
  const accountantFolderName = settings?.accountant_folder_name
  const accountantEmail = settings?.accountant_email
  const mailjetSenderEmail = settings?.mailjet_sender_email
  const { data: mailjetSenderStatus, isLoading: mailjetSenderStatusLoading, isError: mailjetSenderStatusError } = useMailjetSenderStatus(
    mailjetSenderEmail || '',
    Boolean(appConfig?.mailjet_enabled)
  )
  const summaryEmailReady = Boolean(
    accountantEmail
    && mailjetSenderEmail
    && appConfig?.mailjet_enabled
    && mailjetSenderStatus?.active
  )

  const resolveFioToken = async () => {
    if (fioVault?.configured && fioVault.ciphertext && fioVault.nonce && fioVault.salt && fioVault.kdf && fioVault.kdf_params) {
      return unlockStoredSecret({
        ciphertext: fioVault.ciphertext,
        nonce: fioVault.nonce,
        salt: fioVault.salt,
        kdf: fioVault.kdf,
        kdf_params: fioVault.kdf_params,
      })
    }

    const legacyToken = getLegacyFioToken()?.trim()
    if (legacyToken) {
      return legacyToken
    }

    throw new Error('Configure your Fio token in Settings before copying to Accountant')
  }

  const handleExport = () => {
    if (!selectedMonth) return

    const url = `/api/export/${selectedMonth}?mark_exported=${markExported}`
    window.open(url, '_blank')
  }

  const handleCopyToAccountant = async () => {
    if (!selectedMonth || !accountantFolderId) return

    setIsCopying(true)
    try {
      const fioToken = includeMonthlyStatement ? await resolveFioToken() : undefined
      const result = await copyToGDrive.mutateAsync({
        yearMonth: selectedMonth,
        folderId: accountantFolderId,
        markExported,
        includeMonthlyStatement,
        fioToken,
        sendSummaryEmail: true,
      })
      let message = `Copied ${result.copied} invoices`
      if (result.skipped > 0) {
        message += `, ${result.skipped} already existed`
      }
      if (includeMonthlyStatement && result.statement.status === 'uploaded') {
        message += ', uploaded monthly statement'
      } else if (includeMonthlyStatement && result.statement.status === 'skipped') {
        message += ', monthly statement already existed'
      }
      if (result.errors?.length > 0) {
        message += ` (${result.errors.length} errors)`
      }
      if (result.email.status === 'sent') {
        message += `, emailed ${result.email.recipient}`
        showSuccess(message)
      } else {
        showApiError(
          new Error(`Documents were copied, but the summary email failed: ${result.email.error || 'unknown error'}`),
          'Export'
        )
      }
    } catch (error) {
      showApiError(error, 'Copy to GDrive')
    } finally {
      setIsCopying(false)
    }
  }

  const monthOptions = [
    { value: '', label: 'Select a month' },
    ...(dashboard?.available_months?.map((m: string) => ({ value: m, label: m })) || [])
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Export</h1>
      </div>

      {/* Month Selection */}
      <Card>
        <CardHeader>
          <CardTitle>Export Invoices</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div>
                <Label>Select Month</Label>
                <Select
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  options={monthOptions}
                />
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="mark-exported"
                  checked={markExported}
                  onCheckedChange={(checked) => setMarkExported(checked === true)}
                />
                <Label htmlFor="mark-exported" className="text-sm font-normal">
                  Mark invoices as exported after download
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="include-monthly-statement"
                  checked={includeMonthlyStatement}
                  onCheckedChange={(checked) => setIncludeMonthlyStatement(checked === true)}
                />
                <Label htmlFor="include-monthly-statement" className="text-sm font-normal">
                  Include monthly PDF statement
                </Label>
              </div>

              <Button
                onClick={handleExport}
                disabled={!selectedMonth}
                className="w-full"
              >
                <Download className="h-4 w-4 mr-2" />
                Download ZIP
              </Button>

              {gdriveStatus?.authenticated && accountantFolderId && (
                <Button
                  onClick={handleCopyToAccountant}
                  disabled={!selectedMonth || isCopying || !summaryEmailReady}
                  className="w-full"
                >
                  {isCopying ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Cloud className="h-4 w-4 mr-2" />
                  )}
                  Copy & Email Accountant
                </Button>
              )}

              {gdriveStatus?.authenticated && accountantFolderId && !summaryEmailReady && (
                <p className="text-sm text-orange-700">
                  {!accountantEmail
                    ? 'Add the accountant email in Settings before exporting.'
                    : !mailjetSenderEmail
                      ? 'Add the Mailjet sender email in Settings before exporting.'
                    : mailjetSenderStatusLoading
                      ? 'Checking the sender with Mailjet...'
                    : mailjetSenderStatusError
                      ? 'Could not verify the sender with Mailjet.'
                    : appConfig?.mailjet_enabled && mailjetSenderStatus && !mailjetSenderStatus.active
                      ? 'The sender address or domain is not active in Mailjet.'
                    : 'Configure Mailjet on the server before exporting.'}
                </p>
              )}

              {summaryEmailReady && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Mail className="h-4 w-4" />
                  <span>Summary will be sent to {accountantEmail}</span>
                </div>
              )}
            </div>

            {/* Stats for selected month */}
            <div>
              {selectedMonth && (
                <div className="space-y-4">
                  <h3 className="font-medium">Month Statistics</h3>
                  {statsLoading ? (
                    <p className="text-muted-foreground">Loading...</p>
                  ) : stats ? (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <span>Total Invoices:</span>
                        </div>
                        <span className="font-medium">{stats.invoices.total}</span>

                        <div className="flex items-center gap-2">
                          <CheckCircle className="h-4 w-4 text-green-600" />
                          <span>Matched:</span>
                        </div>
                        <span className="font-medium text-green-600">{stats.invoices.matched}</span>

                        <div className="flex items-center gap-2">
                          <span className="w-4 h-4 rounded-full bg-orange-200" />
                          <span>Unmatched:</span>
                        </div>
                        <span className="font-medium text-orange-600">{stats.invoices.unmatched}</span>

                        <div className="flex items-center gap-2">
                          <span className="w-4 h-4 rounded-full bg-blue-200" />
                          <span>Exported:</span>
                        </div>
                        <span className="font-medium text-blue-600">{stats.invoices.exported}</span>
                      </div>

                      <hr />

                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <span className="text-muted-foreground">Transactions:</span>
                        <span className="font-medium">{stats.transactions.total}</span>

                        <span className="text-muted-foreground">Matched:</span>
                        <span className="font-medium">{stats.transactions.matched}</span>

                        <span className="text-muted-foreground">Known:</span>
                        <span className="font-medium">{stats.transactions.known}</span>

                        <span className="text-muted-foreground">Skipped:</span>
                        <span className="font-medium">{stats.transactions.skipped}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No data for this month</p>
                  )}
                </div>
              )}

              {!selectedMonth && (
                <div className="flex items-center justify-center h-32 text-muted-foreground">
                  Select a month to see statistics
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Info */}
      <Card>
        <CardHeader>
          <CardTitle>About Export</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            The export will download a ZIP file containing all matched invoices for the selected month.
          </p>
          <p>
            Invoice month is determined by the invoice date (for VAT purposes), not the payment date.
          </p>
          <p>
            If you check "Mark as exported", the invoices will be marked with an "exported" status
            so you can track which months have been processed.
          </p>
          {accountantFolderId && (
            <p>
              <strong>Copy to Accountant</strong>: Copies invoices to your configured shared folder
              ({accountantFolderName || accountantFolderId}) and routes them by document type into
              `POKLADNICNE_DOKLADY`, `DOSLE_FAKTURY`, or `OSTATNE`. If you enable
              "Include monthly PDF statement", the app also uploads the monthly Fio statement PDF to `OSTATNE`.
              After the copy succeeds, it emails the configured accountant with the period and any comments saved on exported documents.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
