import * as React from "react"
import { Link } from "wouter"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useSession, useMarkKnown, useMatchWithPdf, type Transaction } from "@/api/client"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { SummaryCards } from "@/components/report/SummaryCards"
import { MatchedTable, UnmatchedTable, KnownTable, FeesTable, IncomeTable } from "@/components/report/TransactionTable"
import { MarkKnownModal, type MarkKnownData } from "@/components/report/MarkKnownModal"
import { UploadPdfModal } from "@/components/report/UploadPdfModal"
import { formatDate } from "@/lib/utils"

interface ReportPageProps {
  sessionId: string
}

export function ReportPage({ sessionId }: ReportPageProps) {
  const sessionIdNum = parseInt(sessionId, 10)
  const { data: session, isLoading, error } = useSession(sessionIdNum)
  const markKnown = useMarkKnown()
  const matchWithPdf = useMatchWithPdf()

  const [selectedTab, setSelectedTab] = React.useState("matched")
  const [markKnownTransaction, setMarkKnownTransaction] = React.useState<Transaction | null>(null)
  const [uploadPdfTransaction, setUploadPdfTransaction] = React.useState<Transaction | null>(null)

  const handleMarkKnown = async (data: MarkKnownData) => {
    await markKnown.mutateAsync({ ...data, sessionId: sessionIdNum })
    setMarkKnownTransaction(null)
  }

  const handleUploadPdf = async (file: File) => {
    if (!uploadPdfTransaction) return
    await matchWithPdf.mutateAsync({
      sessionId: sessionIdNum,
      transactionId: uploadPdfTransaction.id,
      file,
    })
    setUploadPdfTransaction(null)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold text-destructive">Error loading report</h2>
        <p className="text-muted-foreground mt-2">{error?.message || "Session not found"}</p>
        <Link href="/wizard">
          <Button className="mt-4">Start New Reconciliation</Button>
        </Link>
      </div>
    )
  }

  if (session.status === "processing") {
    return (
      <div className="text-center py-12">
        <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
        <h2 className="text-xl font-semibold mt-4">Processing...</h2>
        <p className="text-muted-foreground">Please wait while reconciliation completes</p>
      </div>
    )
  }

  if (session.status === "failed") {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold text-destructive">Reconciliation Failed</h2>
        <p className="text-muted-foreground mt-2">{session.error_message}</p>
        <Link href="/wizard">
          <Button className="mt-4">Try Again</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/wizard">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold">Reconciliation Report</h1>
            <p className="text-sm text-muted-foreground">
              {formatDate(session.from_date)} - {formatDate(session.to_date)}
            </p>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <SummaryCards
        matched={session.matched_count}
        review={session.review_count}
        unmatched={session.unmatched_count}
        known={session.known_count}
      />

      {/* Tabs */}
      <Tabs value={selectedTab} onValueChange={setSelectedTab}>
        <TabsList>
          <TabsTrigger value="matched">
            Matched ({session.matched?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="unmatched">
            Unmatched ({session.unmatched?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="known">
            Known ({session.known?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="fees">
            Fees ({session.fees?.length || 0})
          </TabsTrigger>
          <TabsTrigger value="income">
            Income ({session.income?.length || 0})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="matched" className="border rounded-lg">
          <MatchedTable matches={session.matched || []} />
        </TabsContent>

        <TabsContent value="unmatched" className="border rounded-lg">
          <UnmatchedTable
            transactions={session.unmatched || []}
            onMarkKnown={setMarkKnownTransaction}
            onUploadPdf={setUploadPdfTransaction}
          />
        </TabsContent>

        <TabsContent value="known" className="border rounded-lg">
          <KnownTable transactions={session.known || []} />
        </TabsContent>

        <TabsContent value="fees" className="border rounded-lg">
          <FeesTable transactions={session.fees || []} />
        </TabsContent>

        <TabsContent value="income" className="border rounded-lg">
          <IncomeTable transactions={session.income || []} />
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
