import * as React from "react"
import { Link } from "wouter"
import { ArrowLeft, Loader2, RefreshCw, Upload } from "lucide-react"
import { useMonth, useMarkKnownMonthly, useMatchWithPdfMonthly, useMonthInvoices, useMonths, useUploadInvoice, useRenameInvoice, useRenameInvoiceFile, useSkipTransaction, useManualMatch, useApproveMatch, type Transaction } from "@/api/client"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { SummaryCards } from "@/components/report/SummaryCards"
import { MatchedTable, UnmatchedTable, KnownTable, FeesTable, IncomeTable, FolderInvoicesTable } from "@/components/report/TransactionTable"
import { MarkKnownModal, type MarkKnownData } from "@/components/report/MarkKnownModal"
import { UploadPdfModal } from "@/components/report/UploadPdfModal"
import { UploadInvoiceModal } from "@/components/report/UploadInvoiceModal"
import { SkipTransactionModal } from "@/components/report/SkipTransactionModal"
import { ManualMatchModal } from "@/components/report/ManualMatchModal"
import { useSync } from "@/context/SyncContext"

// Calculate previous month
function getPrevMonth(ym: string): string {
  const [year, mon] = ym.split("-").map(Number)
  const prevDate = new Date(year, mon - 2, 1)
  return `${prevDate.getFullYear()}-${String(prevDate.getMonth() + 1).padStart(2, "0")}`
}

interface MonthReportPageProps {
  yearMonth: string
}

export function MonthReportPage({ yearMonth }: MonthReportPageProps) {
  const { data: month, isLoading, error, refetch } = useMonth(yearMonth)
  const { data: months } = useMonths()
  const { data: invoicesData } = useMonthInvoices(yearMonth)
  const markKnown = useMarkKnownMonthly()
  const matchWithPdf = useMatchWithPdfMonthly()
  const uploadInvoice = useUploadInvoice()
  const renameInvoice = useRenameInvoice()
  const renameInvoiceFile = useRenameInvoiceFile()
  const skipTransaction = useSkipTransaction()
  const manualMatch = useManualMatch()
  const approveMatch = useApproveMatch()

  const [selectedTab, setSelectedTab] = React.useState("unmatched")
  const [markKnownTransaction, setMarkKnownTransaction] = React.useState<Transaction | null>(null)
  const [uploadPdfTransaction, setUploadPdfTransaction] = React.useState<Transaction | null>(null)
  const [showUploadInvoice, setShowUploadInvoice] = React.useState(false)
  const [skipTransactionData, setSkipTransactionData] = React.useState<Transaction | null>(null)
  const [manualMatchTransaction, setManualMatchTransaction] = React.useState<Transaction | null>(null)
  const { startSync } = useSync()

  // Helper to get folder info for a month from API data
  const getMonthFolder = React.useCallback((ym: string) => {
    const m = months?.find((x) => x.year_month === ym)
    if (m?.gdrive_folder_id && m?.gdrive_folder_name) {
      return { id: m.gdrive_folder_id, name: m.gdrive_folder_name }
    }
    return null
  }, [months])

  // Format year-month for display
  const formatYearMonth = (ym: string) => {
    const [year, mon] = ym.split("-")
    const date = new Date(parseInt(year), parseInt(mon) - 1)
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  }

  const handleMarkKnown = async (data: MarkKnownData) => {
    await markKnown.mutateAsync({ ...data, yearMonth })
    setMarkKnownTransaction(null)
    window.location.reload()
  }

  const handleUploadPdf = async (file: File, vendor?: string, invoiceDate?: string) => {
    if (!uploadPdfTransaction) return
    await matchWithPdf.mutateAsync({
      yearMonth,
      transactionId: uploadPdfTransaction.id,
      file,
      vendor,
      invoiceDate,
    })
    setUploadPdfTransaction(null)
    window.location.reload()
  }

  const handleResync = () => {
    const fioToken = localStorage.getItem("fio_token")
    if (!fioToken) {
      alert("Fio token not found. Please configure it in Settings.")
      return
    }

    const folderForMonth = getMonthFolder(yearMonth)
    const prevMonthFolder = getMonthFolder(getPrevMonth(yearMonth))

    startSync({
      yearMonth,
      fioToken,
      gdriveFolderId: folderForMonth?.id,
      prevMonthGdriveFolderId: prevMonthFolder?.id,
      onComplete: () => refetch(),
    })
  }

  const handleUploadInvoice = async (file: File, invoiceDate: string) => {
    await uploadInvoice.mutateAsync({
      yearMonth,
      file,
      invoiceDate,
    })
    setShowUploadInvoice(false)
    refetch()
  }

  const handleSkipTransaction = async (reason: string) => {
    if (!skipTransactionData) return
    await skipTransaction.mutateAsync({
      yearMonth,
      transactionId: skipTransactionData.id,
      reason,
    })
    setSkipTransactionData(null)
    refetch()
  }

  const handleManualMatch = async (invoiceFileId: string) => {
    if (!manualMatchTransaction) return
    await manualMatch.mutateAsync({
      yearMonth,
      transactionId: manualMatchTransaction.id,
      invoiceFileId,
    })
    setManualMatchTransaction(null)
    refetch()
  }

  const handleApproveMatch = async (transactionId: string) => {
    await approveMatch.mutateAsync({
      yearMonth,
      transactionId,
    })
    refetch()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !month) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold text-destructive">Error loading report</h2>
        <p className="text-muted-foreground mt-2">{error?.message || "Month not found"}</p>
        <Link href="/">
          <Button className="mt-4">Go Home</Button>
        </Link>
      </div>
    )
  }

  if (month.status === "processing") {
    return (
      <div className="text-center py-12">
        <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
        <h2 className="text-xl font-semibold mt-4">Processing...</h2>
        <p className="text-muted-foreground">Please wait while reconciliation completes</p>
      </div>
    )
  }

  if (month.status === "failed") {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold text-destructive">Reconciliation Failed</h2>
        <p className="text-muted-foreground mt-2">{month.error_message}</p>
        <Button className="mt-4" onClick={handleResync}>
          Try Again
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold">{formatYearMonth(yearMonth)}</h1>
            <p className="text-sm text-muted-foreground">
              Last synced: {month.last_synced_at ? new Date(month.last_synced_at).toLocaleString() : "Never"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setShowUploadInvoice(true)}
          >
            <Upload className="h-4 w-4 mr-2" />
            Add Invoice
          </Button>
          <Button
            variant="outline"
            onClick={handleResync}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Re-sync
          </Button>
        </div>
      </div>

      {/* Summary cards - use actual array lengths for consistency with tabs */}
      <SummaryCards
        matched={month.matched?.filter(m => m.status === 'OK').length || 0}
        review={month.matched?.filter(m => m.status === 'REVIEW').length || 0}
        unmatched={month.unmatched?.length || 0}
        known={month.known?.length || 0}
        skipped={month.skipped?.length || 0}
      />

      {/* Tabs */}
      <Tabs value={selectedTab} onValueChange={setSelectedTab}>
        <TabsList>
          <TabsTrigger value="unmatched">
            Unmatched ({month.unmatched?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="matched">
            Matched ({month.matched?.filter(m => m.status === 'OK').length || 0}
            {(month.matched?.filter(m => m.status === 'REVIEW').length || 0) > 0 &&
              ` + ${month.matched?.filter(m => m.status === 'REVIEW').length} review`})
          </TabsTrigger>
          <TabsTrigger value="known">
            Known ({(month.known?.length || 0) + (month.skipped?.length || 0)})
          </TabsTrigger>
          <TabsTrigger value="fees">
            Fees ({month.fees?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="income">
            Income ({month.income?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="folder-invoices">
            Folder Invoices ({invoicesData?.total || 0})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="unmatched" className="border rounded-lg">
          <UnmatchedTable
            transactions={month.unmatched || []}
            onMarkKnown={setMarkKnownTransaction}
            onUploadPdf={setUploadPdfTransaction}
            onSkip={setSkipTransactionData}
            onManualMatch={setManualMatchTransaction}
          />
        </TabsContent>

        <TabsContent value="matched" className="border rounded-lg">
          <MatchedTable
            matches={month.matched || []}
            onApprove={handleApproveMatch}
            isApproving={approveMatch.isPending}
          />
        </TabsContent>

        <TabsContent value="known" className="border rounded-lg">
          <KnownTable
            transactions={month.known || []}
            skippedTransactions={month.skipped || []}
          />
        </TabsContent>

        <TabsContent value="fees" className="border rounded-lg">
          <FeesTable transactions={month.fees || []} />
        </TabsContent>

        <TabsContent value="income" className="border rounded-lg">
          <IncomeTable transactions={month.income || []} />
        </TabsContent>

        <TabsContent value="folder-invoices" className="border rounded-lg">
          <FolderInvoicesTable
            invoices={invoicesData?.invoices || []}
            formatYearMonth={formatYearMonth}
            onRename={async (fileId, newFilename) => {
              await renameInvoice.mutateAsync({ fileId, newFilename })
              // Refetch to show updated data - user can manually resync to rematch
              refetch()
            }}
            isRenaming={renameInvoice.isPending}
            onReanalyze={async (fileId, vendor, invoiceDate, paymentType) => {
              await renameInvoiceFile.mutateAsync({
                fileId,
                vendor: vendor || "",
                invoiceDate: invoiceDate || "",
                paymentType
              })
              refetch()
            }}
            isReanalyzing={renameInvoiceFile.isPending}
          />
        </TabsContent>
      </Tabs>

      {/* Mark Known Modal */}
      <MarkKnownModal
        transaction={markKnownTransaction}
        open={markKnownTransaction !== null}
        onOpenChange={(open) => !open && setMarkKnownTransaction(null)}
        onSubmit={handleMarkKnown}
        isLoading={markKnown.isPending}
      />

      {/* Upload PDF Modal */}
      <UploadPdfModal
        transaction={uploadPdfTransaction}
        open={uploadPdfTransaction !== null}
        onOpenChange={(open) => !open && setUploadPdfTransaction(null)}
        onSubmit={handleUploadPdf}
        isLoading={matchWithPdf.isPending}
      />

      {/* Upload Invoice Modal */}
      <UploadInvoiceModal
        open={showUploadInvoice}
        onOpenChange={setShowUploadInvoice}
        onSubmit={handleUploadInvoice}
        isLoading={uploadInvoice.isPending}
        yearMonth={yearMonth}
      />

      {/* Skip Transaction Modal */}
      <SkipTransactionModal
        transaction={skipTransactionData}
        open={skipTransactionData !== null}
        onOpenChange={(open) => !open && setSkipTransactionData(null)}
        onSubmit={handleSkipTransaction}
        isLoading={skipTransaction.isPending}
      />

      {/* Manual Match Modal */}
      <ManualMatchModal
        transaction={manualMatchTransaction}
        invoices={invoicesData?.invoices || []}
        open={manualMatchTransaction !== null}
        onOpenChange={(open) => !open && setManualMatchTransaction(null)}
        onSubmit={handleManualMatch}
        isLoading={manualMatch.isPending}
      />
    </div>
  )
}
