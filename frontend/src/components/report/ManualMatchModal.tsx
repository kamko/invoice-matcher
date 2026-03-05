import * as React from "react"
import { Loader2, Search, FileText, Check } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { formatCurrency } from "@/lib/utils"
import type { Transaction, FolderInvoice } from "@/api/client"

interface ManualMatchModalProps {
  transaction: Transaction | null
  invoices: FolderInvoice[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (invoiceFileId: string) => Promise<void>
  isLoading?: boolean
}

export function ManualMatchModal({
  transaction,
  invoices,
  open,
  onOpenChange,
  onSubmit,
  isLoading,
}: ManualMatchModalProps) {
  const [search, setSearch] = React.useState("")
  const [selectedInvoice, setSelectedInvoice] = React.useState<string | null>(null)

  // Reset when modal closes
  React.useEffect(() => {
    if (!open) {
      setSearch("")
      setSelectedInvoice(null)
    }
  }, [open])

  // Filter invoices by search (include all, not just unpaid - for multi-receipt PDFs)
  const filteredInvoices = React.useMemo(() => {
    return invoices
      .filter(inv => {
        if (!search) return true
        const searchLower = search.toLowerCase()
        return (
          inv.filename.toLowerCase().includes(searchLower) ||
          inv.vendor?.toLowerCase().includes(searchLower) ||
          inv.amount?.includes(search)
        )
      })
      // Sort unpaid first
      .sort((a, b) => {
        if (a.status === "unpaid" && b.status !== "unpaid") return -1
        if (a.status !== "unpaid" && b.status === "unpaid") return 1
        return 0
      })
  }, [invoices, search])

  const handleSubmit = async () => {
    if (selectedInvoice) {
      await onSubmit(selectedInvoice)
    }
  }

  if (!transaction) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Manual Match</DialogTitle>
          <DialogDescription>
            Select an invoice to match with this transaction
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Transaction info */}
          <div className="rounded-lg bg-muted p-3 text-sm">
            <div className="font-medium">Transaction Details</div>
            <div className="mt-1 grid grid-cols-2 gap-1 text-muted-foreground">
              <span>Date:</span>
              <span>{transaction.date}</span>
              <span>Amount:</span>
              <span className="font-mono">
                {formatCurrency(transaction.amount, transaction.currency)}
              </span>
              <span>Counter Party:</span>
              <span className="truncate">{transaction.counter_name || "-"}</span>
              <span>VS:</span>
              <span className="font-mono">{transaction.vs || "-"}</span>
            </div>
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search invoices by name, vendor, or amount..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Invoice list */}
          <div className="h-[250px] overflow-y-auto rounded-md border">
            {filteredInvoices.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">
                No invoices found
              </div>
            ) : (
              <div className="p-2 space-y-1">
                {filteredInvoices.map((inv) => (
                  <button
                    key={inv.gdrive_file_id}
                    onClick={() => setSelectedInvoice(inv.gdrive_file_id)}
                    className={`
                      w-full text-left p-3 rounded-md transition-colors
                      flex items-center gap-3
                      ${selectedInvoice === inv.gdrive_file_id
                        ? "bg-primary text-primary-foreground"
                        : "hover:bg-muted"
                      }
                    `}
                  >
                    <FileText className="h-5 w-5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate flex items-center gap-2">
                        {inv.filename}
                        {inv.status === "paid" && (
                          <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                            matched
                          </span>
                        )}
                      </div>
                      <div className="text-sm opacity-80 flex gap-4">
                        {inv.vendor && <span>{inv.vendor}</span>}
                        {inv.amount && <span className="font-mono">{inv.amount}</span>}
                      </div>
                    </div>
                    {selectedInvoice === inv.gdrive_file_id && (
                      <Check className="h-5 w-5 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!selectedInvoice || isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Match
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
