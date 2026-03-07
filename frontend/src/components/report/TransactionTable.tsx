import * as React from "react"
import { Upload, ExternalLink, Check, Clock, Undo2, Pencil, Link, RefreshCw, MoreVertical, Trash2 } from "lucide-react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { formatCurrency, formatDate } from "@/lib/utils"
import type { Transaction, MatchResult, FolderInvoice } from "@/api/client"
import { RenameInvoiceModal } from "./RenameInvoiceModal"
import { ReanalyzeInvoiceModal } from "./ReanalyzeInvoiceModal"

interface MatchedTableProps {
  matches: MatchResult[]
  onApprove?: (transactionId: string) => void
  isApproving?: boolean
}

export function MatchedTable({ matches, onApprove, isApproving }: MatchedTableProps) {
  const hasReviewItems = matches.some(m => m.status === "REVIEW")

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
          {hasReviewItems && onApprove && <TableHead>Actions</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {matches.length === 0 ? (
          <TableRow>
            <TableCell colSpan={hasReviewItems && onApprove ? 8 : 7} className="text-center text-muted-foreground">
              No matched transactions
            </TableCell>
          </TableRow>
        ) : (
          matches.map((match, index) => (
            <TableRow key={match.transaction?.id || `cash-${index}`}>
              <TableCell>{match.transaction ? formatDate(match.transaction.date) : (match.invoice?.invoice_date || "-")}</TableCell>
              <TableCell className="font-mono">
                {match.transaction
                  ? formatCurrency(match.transaction.amount, match.transaction.currency)
                  : (match.invoice?.amount ? `€${match.invoice.amount}` : "-")}
              </TableCell>
              <TableCell className="max-w-[200px] truncate">
                {match.transaction
                  ? (match.transaction.counter_name || match.transaction.counter_account)
                  : (match.invoice?.payment_type === "cash" ? "Cash Payment" : "-")}
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
              {hasReviewItems && onApprove && (
                <TableCell>
                  {match.status === "REVIEW" && match.transaction && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onApprove(match.transaction!.id)}
                      disabled={isApproving}
                    >
                      <Check className="h-4 w-4 mr-1" />
                      Approve
                    </Button>
                  )}
                </TableCell>
              )}
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
  onDelete?: (fileId: string) => Promise<void>
  isDeleting?: boolean
}

export function FolderInvoicesTable({ invoices, formatYearMonth, onRename, isRenaming, onReanalyze, isReanalyzing, onDelete, isDeleting }: FolderInvoicesTableProps) {
  const [renameInvoice, setRenameInvoice] = React.useState<FolderInvoice | null>(null)
  const [reanalyzeInvoice, setReanalyzeInvoice] = React.useState<FolderInvoice | null>(null)
  const [deleteConfirm, setDeleteConfirm] = React.useState<FolderInvoice | null>(null)

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

  const handleDelete = async () => {
    if (onDelete && deleteConfirm) {
      await onDelete(deleteConfirm.gdrive_file_id)
      setDeleteConfirm(null)
    }
  }

  return (
    <>
      {/* Delete Confirmation Dialog */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-lg p-6 max-w-md shadow-lg">
            <h3 className="text-lg font-semibold text-destructive">Delete Invoice</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This will permanently delete the invoice from Google Drive and remove all related records.
            </p>
            <p className="mt-2 font-mono text-sm bg-muted p-2 rounded truncate">
              {deleteConfirm.filename}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? "Deleting..." : "Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
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
              {(onRename || onReanalyze || onDelete) && (
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {onReanalyze && (
                        <DropdownMenuItem onClick={() => setReanalyzeInvoice(inv)}>
                          <RefreshCw className="h-4 w-4 mr-2" />
                          Re-analyze
                        </DropdownMenuItem>
                      )}
                      {onRename && (
                        <DropdownMenuItem onClick={() => setRenameInvoice(inv)}>
                          <Pencil className="h-4 w-4 mr-2" />
                          Rename
                        </DropdownMenuItem>
                      )}
                      {onDelete && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => setDeleteConfirm(inv)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Delete
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
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
