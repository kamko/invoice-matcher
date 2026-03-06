import * as React from "react"
import { Loader2, RefreshCw, FileSearch } from "lucide-react"
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
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import type { FolderInvoice } from "@/api/client"
import { useParseCachedInvoice } from "@/api/client"

const PAYMENT_TYPES = [
  { value: "card", label: "Card" },
  { value: "wire", label: "Wire Transfer" },
  { value: "sepa-debit", label: "SEPA Direct Debit" },
  { value: "cash", label: "Cash" },
  { value: "credit-note", label: "Credit Note" },
]

interface ReanalyzeInvoiceModalProps {
  invoice: FolderInvoice | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onReanalyze: (fileId: string, vendor?: string, invoiceDate?: string, paymentType?: string) => Promise<void>
  isLoading?: boolean
}

export function ReanalyzeInvoiceModal({
  invoice,
  open,
  onOpenChange,
  onReanalyze,
  isLoading,
}: ReanalyzeInvoiceModalProps) {
  const [vendor, setVendor] = React.useState("")
  const [invoiceDate, setInvoiceDate] = React.useState("")
  const [paymentType, setPaymentType] = React.useState("card")
  const [amount, setAmount] = React.useState<string | null>(null)
  const [isParsed, setIsParsed] = React.useState(false)
  const parseCached = useParseCachedInvoice()

  // Reset form when modal opens/closes or invoice changes
  React.useEffect(() => {
    if (open && invoice) {
      // Reset to current values from database
      setVendor(invoice.vendor || "")
      setAmount(invoice.amount || null)
      // Try to extract date from filename (YYYY-MM-DD-NNN_...)
      const dateMatch = invoice.filename.match(/^(\d{4}-\d{2}-\d{2})/)
      setInvoiceDate(dateMatch ? dateMatch[1] : "")
      // Extract payment type from filename
      const parts = invoice.filename.split("_")
      const extractedType = parts.length >= 2 ? parts[1] : "card"
      // Validate it's a known type
      const knownType = PAYMENT_TYPES.find(t => t.value === extractedType)
      setPaymentType(knownType ? extractedType : "card")
      setIsParsed(false)
    }
  }, [open, invoice])

  const handleLoadFromFile = async () => {
    if (!invoice) return
    try {
      const result = await parseCached.mutateAsync(invoice.gdrive_file_id)
      if (result.success) {
        setVendor(result.vendor || "")
        setAmount(result.amount)
        setInvoiceDate(result.invoice_date || "")
        setIsParsed(true)
      }
    } catch (error) {
      console.error("Failed to parse:", error)
    }
  }

  const handleConfirm = async () => {
    if (invoice) {
      await onReanalyze(invoice.gdrive_file_id, vendor || undefined, invoiceDate || undefined, paymentType)
    }
  }

  if (!invoice) return null

  // Generate preview filename - matches backend slugify_vendor()
  const vendorSlug = vendor
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')  // Remove special chars except spaces/hyphens
    .replace(/\s+/g, '-')       // Replace spaces with hyphens
    .replace(/-+/g, '-')        // Collapse multiple hyphens
    .replace(/^-|-$/g, '')      // Strip leading/trailing hyphens
    .slice(0, 20)
  const previewFilename = invoiceDate && vendorSlug
    ? `${invoiceDate}-001_${paymentType}_${vendorSlug}.pdf`
    : invoice.filename

  const isParsing = parseCached.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Re-analyze Invoice
          </DialogTitle>
          <DialogDescription>
            Load data from PDF, review/edit, then confirm to rename the file.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Current file info */}
          <div className="rounded-lg bg-muted p-3 text-sm">
            <div className="font-medium">Current File</div>
            <div className="mt-1 font-mono text-muted-foreground truncate">
              {invoice.filename}
            </div>
          </div>

          {/* Step 1: Load from file button */}
          <div className="flex justify-center">
            <Button
              variant={isParsed ? "outline" : "default"}
              onClick={handleLoadFromFile}
              disabled={isParsing}
              className="w-full"
            >
              {isParsing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Parsing PDF...
                </>
              ) : (
                <>
                  <FileSearch className="mr-2 h-4 w-4" />
                  {isParsed ? "Re-load from file" : "1. Load from file"}
                </>
              )}
            </Button>
          </div>

          {/* Step 2: Editable fields (shown after parsing or with existing data) */}
          <div className={`grid gap-4 ${!isParsed && !invoice.vendor ? 'opacity-50' : ''}`}>
            <div className="grid grid-cols-4 items-center gap-2">
              <Label htmlFor="vendor" className="text-right">
                Vendor:
              </Label>
              <Input
                id="vendor"
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                className="col-span-3"
                placeholder="Company name"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-2">
              <Label htmlFor="date" className="text-right">
                Date:
              </Label>
              <Input
                id="date"
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-2">
              <Label htmlFor="paymentType" className="text-right">
                Type:
              </Label>
              <div className="col-span-3">
                <Select
                  id="paymentType"
                  value={paymentType}
                  onChange={(e) => setPaymentType(e.target.value)}
                  options={PAYMENT_TYPES}
                />
              </div>
            </div>

            <div className="grid grid-cols-4 items-center gap-2">
              <Label className="text-right text-muted-foreground">
                Amount:
              </Label>
              <span className="col-span-3 font-mono">
                {amount ? `${amount}` : (invoice.amount ? `${invoice.amount}` : "-")}
              </span>
            </div>
          </div>

          {/* Preview new filename */}
          {(vendor || invoiceDate) && previewFilename !== invoice.filename && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm">
              <div className="font-medium text-green-700">New Filename</div>
              <div className="mt-1 font-mono text-green-800 truncate">
                {previewFilename}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isLoading || !vendor || !invoiceDate}
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            2. Confirm & Rename
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
