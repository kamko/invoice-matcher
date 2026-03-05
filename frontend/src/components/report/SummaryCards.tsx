import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle, AlertCircle, HelpCircle, Bookmark } from "lucide-react"

interface SummaryCardsProps {
  matched: number
  review: number
  unmatched: number
  known: number
  skipped?: number
}

export function SummaryCards({ matched, review, unmatched, known, skipped = 0 }: SummaryCardsProps) {
  // Known includes both rule-matched and skipped transactions
  const totalKnown = known + skipped
  return (
    <div className="grid gap-4 md:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Matched</CardTitle>
          <CheckCircle className="h-4 w-4 text-green-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-600">{matched}</div>
          <p className="text-xs text-muted-foreground">
            Transactions with matching invoices
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Review</CardTitle>
          <AlertCircle className="h-4 w-4 text-yellow-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-yellow-600">{review}</div>
          <p className="text-xs text-muted-foreground">
            Low confidence matches
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Unmatched</CardTitle>
          <HelpCircle className="h-4 w-4 text-red-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-red-600">{unmatched}</div>
          <p className="text-xs text-muted-foreground">
            No matching invoice found
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Known</CardTitle>
          <Bookmark className="h-4 w-4 text-blue-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-blue-600">{totalKnown}</div>
          <p className="text-xs text-muted-foreground">
            Rules ({known}) + Skipped ({skipped})
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
