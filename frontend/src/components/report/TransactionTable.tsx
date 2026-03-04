import { Upload } from "lucide-react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { formatCurrency, formatDate } from "@/lib/utils"
import type { Transaction, MatchResult } from "@/api/client"

interface MatchedTableProps {
  matches: MatchResult[]
}

export function MatchedTable({ matches }: MatchedTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Counter Party</TableHead>
          <TableHead>Invoice</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {matches.length === 0 ? (
          <TableRow>
            <TableCell colSpan={6} className="text-center text-muted-foreground">
              No matched transactions
            </TableCell>
          </TableRow>
        ) : (
          matches.map((match) => (
            <TableRow key={match.transaction.id}>
              <TableCell>{formatDate(match.transaction.date)}</TableCell>
              <TableCell className="font-mono">
                {formatCurrency(match.transaction.amount, match.transaction.currency)}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">
                {match.transaction.counter_name || match.transaction.counter_account}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">
                {match.invoice?.filename || "-"}
              </TableCell>
              <TableCell>
                <span className="font-mono">{match.confidence_pct}%</span>
              </TableCell>
              <TableCell>
                <Badge
                  variant={
                    match.status === "OK"
                      ? "success"
                      : match.status === "REVIEW"
                      ? "warning"
                      : "destructive"
                  }
                >
                  {match.status}
                </Badge>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

interface UnmatchedTableProps {
  transactions: Transaction[]
  onMarkKnown?: (transaction: Transaction) => void
  onUploadPdf?: (transaction: Transaction) => void
}

export function UnmatchedTable({ transactions, onMarkKnown, onUploadPdf }: UnmatchedTableProps) {
  const hasActions = onMarkKnown || onUploadPdf

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Counter Party</TableHead>
          <TableHead>Note</TableHead>
          <TableHead>VS</TableHead>
          {hasActions && <TableHead>Actions</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={hasActions ? 6 : 5}
              className="text-center text-muted-foreground"
            >
              No unmatched transactions
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{formatDate(t.date)}</TableCell>
              <TableCell className="font-mono">
                {formatCurrency(t.amount, t.currency)}
              </TableCell>
              <TableCell className="max-w-[150px] truncate">
                {t.counter_name || t.counter_account}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">{t.note}</TableCell>
              <TableCell className="font-mono">{t.vs || "-"}</TableCell>
              {hasActions && (
                <TableCell>
                  <div className="flex gap-1">
                    {onUploadPdf && (
                      <Button
                        size="sm"
                        variant="default"
                        onClick={() => onUploadPdf(t)}
                        title="Upload invoice PDF"
                      >
                        <Upload className="h-4 w-4 mr-1" />
                        Upload
                      </Button>
                    )}
                    {onMarkKnown && (
                      <Button size="sm" variant="outline" onClick={() => onMarkKnown(t)}>
                        Skip
                      </Button>
                    )}
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

interface KnownTableProps {
  transactions: Transaction[]
}

export function KnownTable({ transactions }: KnownTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Counter Party</TableHead>
          <TableHead>Reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell colSpan={4} className="text-center text-muted-foreground">
              No known transactions
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{formatDate(t.date)}</TableCell>
              <TableCell className="font-mono">
                {formatCurrency(t.amount, t.currency)}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">
                {t.counter_name || t.counter_account}
              </TableCell>
              <TableCell>{t.rule_reason || "-"}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

interface FeesTableProps {
  transactions: Transaction[]
}

export function FeesTable({ transactions }: FeesTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Note</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell colSpan={4} className="text-center text-muted-foreground">
              No bank fees
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{formatDate(t.date)}</TableCell>
              <TableCell className="font-mono">
                {formatCurrency(t.amount, t.currency)}
              </TableCell>
              <TableCell>
                <Badge variant="outline">Fee</Badge>
              </TableCell>
              <TableCell className="max-w-[300px] truncate">{t.note || "-"}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

interface IncomeTableProps {
  transactions: Transaction[]
}

export function IncomeTable({ transactions }: IncomeTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>From</TableHead>
          <TableHead>Note</TableHead>
          <TableHead>VS</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell colSpan={5} className="text-center text-muted-foreground">
              No income transactions
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{formatDate(t.date)}</TableCell>
              <TableCell className="font-mono text-green-600">
                +{formatCurrency(t.amount, t.currency)}
              </TableCell>
              <TableCell className="max-w-[150px] truncate">
                {t.counter_name || t.counter_account || "-"}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">{t.note || "-"}</TableCell>
              <TableCell className="font-mono">{t.vs || "-"}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}
