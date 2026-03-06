import * as React from "react"
import { Upload, ExternalLink, Check, Clock, Undo2, Pencil, Link, RefreshCw } from "lucide-react"
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
import type { Transaction, MatchResult, FolderInvoice } from "@/api/client"
import { RenameInvoiceModal } from "./RenameInvoiceModal"
import { ReanalyzeInvoiceModal } from "./ReanalyzeInvoiceModal"

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
          <TableHead>Vendor</TableHead>
          <TableHead>Invoice</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {matches.length === 0 ? (
          <TableRow>
            <TableCell colSpan={7} className="text-center text-muted-foreground">
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
              <TableCell className="max-w-[150px] truncate" title={match.invoice?.vendor || ""}>
                {match.invoice?.vendor || "-"}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">
                {match.invoice?.gdrive_file_id ? (
                  <a
                    href={`https://drive.google.com/file/d/${match.invoice.gdrive_file_id}/view`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-blue-600 hover:underline"
                  >
                    {match.invoice.filename}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ) : (
                  match.invoice?.filename || "-"
                )}
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
  onSkip?: (transaction: Transaction) => void
  onManualMatch?: (transaction: Transaction) => void
}

export function UnmatchedTable({ transactions, onMarkKnown, onUploadPdf, onSkip, onManualMatch }: UnmatchedTableProps) {
  const hasActions = onMarkKnown || onUploadPdf || onSkip || onManualMatch

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Counter Party</TableHead>
          <TableHead>Account</TableHead>
          <TableHead>Note</TableHead>
          <TableHead>VS</TableHead>
          {hasActions && <TableHead>Actions</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={hasActions ? 7 : 6}
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
              <TableCell className="max-w-[150px] truncate" title={t.counter_name}>
                {t.counter_name || "-"}
              </TableCell>
              <TableCell className="font-mono text-xs max-w-[180px] truncate" title={t.counter_account}>
                {t.counter_account || "-"}
              </TableCell>
              <TableCell className="max-w-[180px] truncate" title={t.note}>{t.note}</TableCell>
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
                    {onManualMatch && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onManualMatch(t)}
                        title="Match with existing invoice from folder"
                      >
                        <Link className="h-4 w-4 mr-1" />
                        Match
                      </Button>
                    )}
                    {onSkip && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onSkip(t)}
                        title="Skip this transaction (one-time, no rule)"
                      >
                        Skip
                      </Button>
                    )}
                    {onMarkKnown && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onMarkKnown(t)}
                        title="Create a rule to match similar transactions"
                      >
                        Rule
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
  skippedTransactions?: Transaction[]
}

export function KnownTable({ transactions, skippedTransactions = [] }: KnownTableProps) {
  const allTransactions = [
    ...transactions.map(t => ({ ...t, type: 'rule' as const })),
    ...skippedTransactions.map(t => ({ ...t, type: 'skipped' as const })),
  ]

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Counter Party</TableHead>
          <TableHead>Note</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {allTransactions.length === 0 ? (
          <TableRow>
            <TableCell colSpan={6} className="text-center text-muted-foreground">
              No known transactions
            </TableCell>
          </TableRow>
        ) : (
          allTransactions.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{formatDate(t.date)}</TableCell>
              <TableCell className="font-mono">
                {formatCurrency(t.amount, t.currency)}
              </TableCell>
              <TableCell className="max-w-[150px] truncate" title={t.counter_name || t.counter_account || ""}>
                {t.counter_name || t.counter_account}
              </TableCell>
              <TableCell className="max-w-[200px] truncate" title={t.note || ""}>
                {t.note || "-"}
              </TableCell>
              <TableCell>
                <Badge variant={t.type === 'rule' ? 'default' : 'secondary'}>
                  {t.type === 'rule' ? 'Rule' : 'Skipped'}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {t.type === 'rule' ? (t.rule_reason || "-") : (t.skip_reason || "Skipped")}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

interface SkippedTableProps {
  transactions: Transaction[]
  onUnskip?: (transaction: Transaction) => void
}

export function SkippedTable({ transactions, onUnskip }: SkippedTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Counter Party</TableHead>
          <TableHead>Note</TableHead>
          <TableHead>Skip Reason</TableHead>
          {onUnskip && <TableHead>Actions</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell colSpan={onUnskip ? 6 : 5} className="text-center text-muted-foreground">
              No skipped transactions
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{formatDate(t.date)}</TableCell>
              <TableCell className="font-mono">
                {formatCurrency(t.amount, t.currency)}
              </TableCell>
              <TableCell className="max-w-[150px] truncate" title={t.counter_name || t.counter_account || ""}>
                {t.counter_name || t.counter_account}
              </TableCell>
              <TableCell className="max-w-[200px] truncate" title={t.note || ""}>
                {t.note || "-"}
              </TableCell>
              <TableCell className="text-muted-foreground">{t.skip_reason || "Skipped"}</TableCell>
              {onUnskip && (
                <TableCell>
                  <Button size="sm" variant="ghost" onClick={() => onUnskip(t)}>
                    <Undo2 className="h-4 w-4 mr-1" />
                    Undo
                  </Button>
                </TableCell>
              )}
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

interface FolderInvoicesTableProps {
  invoices: FolderInvoice[]
  formatYearMonth: (ym: string) => string
  onRename?: (fileId: string, newFilename: string) => Promise<void>
  isRenaming?: boolean
  onReanalyze?: (fileId: string, vendor?: string, invoiceDate?: string, paymentType?: string) => Promise<void>
  isReanalyzing?: boolean
}

export function FolderInvoicesTable({ invoices, formatYearMonth, onRename, isRenaming, onReanalyze, isReanalyzing }: FolderInvoicesTableProps) {
  const [renameInvoice, setRenameInvoice] = React.useState<FolderInvoice | null>(null)
  const [reanalyzeInvoice, setReanalyzeInvoice] = React.useState<FolderInvoice | null>(null)

  // Helper to detect credit notes from filename
  const isCreditNote = (filename: string) => {
    const lower = filename.toLowerCase()
    return lower.includes("credit-note") || lower.includes("credit_note")
  }

  // Helper to render status badge
  const renderStatus = (inv: FolderInvoice) => {
    const creditNote = isCreditNote(inv.filename)

    if (inv.status === "paid") {
      // Matched with a transaction
      if (creditNote) {
        return (
          <Badge variant="success" className="flex items-center gap-1 w-fit">
            <Undo2 className="h-3 w-3" />
            Credited
          </Badge>
        )
      }
      return (
        <Badge variant="success" className="flex items-center gap-1 w-fit">
          <Check className="h-3 w-3" />
          Paid
        </Badge>
      )
    }

    // Not matched yet
    if (creditNote) {
      return (
        <Badge variant="outline" className="flex items-center gap-1 w-fit">
          <Undo2 className="h-3 w-3" />
          Pending Refund
        </Badge>
      )
    }
    return (
      <Badge variant="warning" className="flex items-center gap-1 w-fit">
        <Clock className="h-3 w-3" />
        Unpaid
      </Badge>
    )
  }

  const handleRename = async (fileId: string, newFilename: string) => {
    if (onRename) {
      await onRename(fileId, newFilename)
      setRenameInvoice(null)
    }
  }

  const handleReanalyze = async (fileId: string, vendor?: string, invoiceDate?: string, paymentType?: string) => {
    if (onReanalyze) {
      await onReanalyze(fileId, vendor, invoiceDate, paymentType)
      setReanalyzeInvoice(null)
    }
  }

  return (
    <>
      <RenameInvoiceModal
        invoice={renameInvoice}
        open={renameInvoice !== null}
        onOpenChange={(open) => !open && setRenameInvoice(null)}
        onRename={handleRename}
        isLoading={isRenaming}
      />
      <ReanalyzeInvoiceModal
        invoice={reanalyzeInvoice}
        open={reanalyzeInvoice !== null}
        onOpenChange={(open) => !open && setReanalyzeInvoice(null)}
        onReanalyze={handleReanalyze}
        isLoading={isReanalyzing}
      />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Filename</TableHead>
            <TableHead>Vendor</TableHead>
            <TableHead>Amount</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Settled In</TableHead>
            {onRename && <TableHead className="w-[60px]">Actions</TableHead>}
          </TableRow>
        </TableHeader>
      <TableBody>
        {invoices.length === 0 ? (
          <TableRow>
            <TableCell colSpan={5} className="text-center text-muted-foreground">
              No invoices in folder. Re-sync to populate.
            </TableCell>
          </TableRow>
        ) : (
          invoices.map((inv) => (
            <TableRow key={inv.gdrive_file_id}>
              <TableCell>
                <a
                  href={`https://drive.google.com/file/d/${inv.gdrive_file_id}/view`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-blue-600 hover:underline"
                >
                  {inv.filename}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </TableCell>
              <TableCell className="max-w-[150px] truncate">{inv.vendor || "-"}</TableCell>
              <TableCell className="font-mono">
                {inv.amount ? `€${inv.amount}` : "-"}
              </TableCell>
              <TableCell>
                {renderStatus(inv)}
              </TableCell>
              <TableCell>
                {inv.paid_month ? (
                  <span className="text-muted-foreground">
                    {formatYearMonth(inv.paid_month)}
                  </span>
                ) : (
                  "-"
                )}
              </TableCell>
              {(onRename || onReanalyze) && (
                <TableCell>
                  <div className="flex gap-1">
                    {onReanalyze && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setReanalyzeInvoice(inv)}
                        title="Re-analyze invoice (re-extract vendor, amount, date)"
                      >
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    )}
                    {onRename && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setRenameInvoice(inv)}
                        title="Rename invoice"
                      >
                        <Pencil className="h-4 w-4" />
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
    </>
  )
}
