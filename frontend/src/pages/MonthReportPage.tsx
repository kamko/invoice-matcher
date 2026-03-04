import * as React from "react"
import { Link } from "wouter"
import { ArrowLeft, Loader2, RefreshCw } from "lucide-react"
import { useMonth, useMarkKnownMonthly, useMatchWithPdfMonthly, useSyncMonth, type Transaction } from "@/api/client"

// Helper to get folder ID for a month from localStorage
function getMonthFolder(yearMonth: string): string {
  const folders = JSON.parse(localStorage.getItem("month_folders") || "{}")
  return folders[yearMonth] || ""
}

// Calculate previous month
function getPrevMonth(ym: string): string {
  const [year, mon] = ym.split("-").map(Number)
  const prevDate = new Date(year, mon - 2, 1)
  return `${prevDate.getFullYear()}-${String(prevDate.getMonth() + 1).padStart(2, "0")}`
}
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { SummaryCards } from "@/components/report/SummaryCards"
import { MatchedTable, UnmatchedTable, KnownTable, FeesTable, IncomeTable } from "@/components/report/TransactionTable"
import { MarkKnownModal, type MarkKnownData } from "@/components/report/MarkKnownModal"
import { UploadPdfModal } from "@/components/report/UploadPdfModal"

interface MonthReportPageProps {
  yearMonth: string
}

export function MonthReportPage({ yearMonth }: MonthReportPageProps) {
  const { data: month, isLoading, error } = useMonth(yearMonth)
  const markKnown = useMarkKnownMonthly()
  const matchWithPdf = useMatchWithPdfMonthly()
  const syncMonth = useSyncMonth()

  const [selectedTab, setSelectedTab] = React.useState("unmatched")
  const [markKnownTransaction, setMarkKnownTransaction] = React.useState<Transaction | null>(null)
  const [uploadPdfTransaction, setUploadPdfTransaction] = React.useState<Transaction | null>(null)

  // Format year-month for display
  const formatYearMonth = (ym: string) => {
    const [year, mon] = ym.split("-")
    const date = new Date(parseInt(year), parseInt(mon) - 1)
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  }

  const handleMarkKnown = async (data: MarkKnownData) => {
    await markKnown.mutateAsync({ ...data, yearMonth })
    setMarkKnownTransaction(null)
  }

  const handleUploadPdf = async (file: File) => {
    if (!uploadPdfTransaction) return
    await matchWithPdf.mutateAsync({
      yearMonth,
      transactionId: uploadPdfTransaction.id,
      file,
    })
    setUploadPdfTransaction(null)
  }

  const handleResync = () => {
    // Get stored token from localStorage
    const fioToken = localStorage.getItem("fio_token")

    if (!fioToken) {
      alert("Fio token not found. Please configure it in Settings.")
      return
    }

    // Get folder for this month and previous month
    const folderForMonth = getMonthFolder(yearMonth)
    const prevMonth = getPrevMonth(yearMonth)
    const prevMonthFolder = getMonthFolder(prevMonth)

    syncMonth.mutate({
      yearMonth,
      year_month: yearMonth,
      fio_token: fioToken,
      gdrive_folder_id: folderForMonth || undefined,
      prev_month_gdrive_folder_id: prevMonthFolder || undefined,
    })
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
        <Button
          variant="outline"
          onClick={handleResync}
          disabled={syncMonth.isPending}
        >
          {syncMonth.isPending ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          Re-sync
        </Button>
      </div>

      {/* Summary cards */}
      <SummaryCards
        matched={month.matched_count}
        review={month.review_count}
        unmatched={month.unmatched_count}
        known={month.known_count}
      />

      {/* Tabs */}
      <Tabs value={selectedTab} onValueChange={setSelectedTab}>
        <TabsList>
          <TabsTrigger value="unmatched">
            Unmatched ({month.unmatched?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="matched">
            Matched ({month.matched?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="known">
            Known ({month.known?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="fees">
            Fees ({month.fees?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="income">
            Income ({month.income?.length || 0})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="unmatched" className="border rounded-lg">
          <UnmatchedTable
            transactions={month.unmatched || []}
            onMarkKnown={setMarkKnownTransaction}
            onUploadPdf={setUploadPdfTransaction}
          />
        </TabsContent>

        <TabsContent value="matched" className="border rounded-lg">
          <MatchedTable matches={month.matched || []} />
        </TabsContent>

        <TabsContent value="known" className="border rounded-lg">
          <KnownTable transactions={month.known || []} />
        </TabsContent>

        <TabsContent value="fees" className="border rounded-lg">
          <FeesTable transactions={month.fees || []} />
        </TabsContent>

        <TabsContent value="income" className="border rounded-lg">
          <IncomeTable transactions={month.income || []} />
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
    </div>
  )
}
