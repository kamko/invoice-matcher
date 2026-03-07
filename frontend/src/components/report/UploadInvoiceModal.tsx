import * as React from "react"
import { Loader2, Upload, FileSearch } from "lucide-react"
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
import { useParsePdf } from "@/api/client"

const PAYMENT_TYPES = [
  { value: "card", label: "Card" },
  { value: "wire", label: "Wire Transfer" },
  { value: "sepa-debit", label: "SEPA Direct Debit" },
  { value: "cash", label: "Cash" },
  { value: "credit-note", label: "Credit Note" },
]

interface UploadInvoiceModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (file: File, invoiceDate: string, vendor?: string, paymentType?: string) => Promise<void>
  isLoading: boolean
  yearMonth: string
}

export function UploadInvoiceModal({
  open,
  onOpenChange,
  onSubmit,
  isLoading,
  yearMonth,
}: UploadInvoiceModalProps) {
  const [file, setFile] = React.useState<File | null>(null)
  const [vendor, setVendor] = React.useState("")
  const [invoiceDate, setInvoiceDate] = React.useState("")
  const [paymentType, setPaymentType] = React.useState("card")
  const [amount, setAmount] = React.useState<string | null>(null)
  const [isParsed, setIsParsed] = React.useState(false)
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const parsePdf = useParsePdf()

  // Reset form when modal opens/closes
  React.useEffect(() => {
    if (open) {
      // Default to last day of the month
      const [year, month] = yearMonth.split("-").map(Number)
      const lastDay = new Date(year, month, 0).getDate()
      setInvoiceDate(`${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`)
      setFile(null)
      setVendor("")
      setAmount(null)
      setPaymentType("card")
      setIsParsed(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
  }, [open, yearMonth])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile && selectedFile.type === "application/pdf") {
      setFile(selectedFile)
      setIsParsed(false)
      setVendor("")
      setAmount(null)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && droppedFile.type === "application/pdf") {
      setFile(droppedFile)
      setIsParsed(false)
      setVendor("")
      setAmount(null)
    }
  }

  const handleParseFile = async () => {
    if (!file) return
    try {
      const result = await parsePdf.mutateAsync(file)
      if (result.success) {
        setVendor(result.vendor || "")
        setAmount(result.amount)
        if (result.invoice_date) {
          setInvoiceDate(result.invoice_date)
        }
        setIsParsed(true)
      }
    } catch (error) {
      console.error("Failed to parse:", error)
    }
  }

  const handleSubmit = async () => {
    if (!file || !invoiceDate) return
    await onSubmit(file, invoiceDate, vendor || undefined, paymentType)
    setFile(null)
    setVendor("")
    setAmount(null)
    setIsParsed(false)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleClose = (open: boolean) => {
    if (!open) {
      setFile(null)
      setVendor("")
      setAmount(null)
      setIsParsed(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
    onOpenChange(open)
  }

  const formatYearMonth = (ym: string) => {
    const [year, mon] = ym.split("-")
    const date = new Date(parseInt(year), parseInt(mon) - 1)
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  }

  // Generate preview filename
  const vendorSlug = vendor
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 20)
  const previewFilename = invoiceDate && vendorSlug
    ? `${invoiceDate}-001_${paymentType}_${vendorSlug}.pdf`
    : null

  const isParsing = parsePdf.isPending

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Upload Invoice</DialogTitle>
          <DialogDescription>
            Add a new invoice to {formatYearMonth(yearMonth)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Step 1: File Upload */}
          <div className="space-y-2">
            <Label>1. Select PDF File</Label>
            <div
              className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
                file ? "border-green-500 bg-green-50" : "border-muted-foreground/25 hover:border-primary"
              }`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                onChange={handleFileChange}
                className="hidden"
              />
              {file ? (
                <div className="space-y-1">
                  <Upload className="h-6 w-6 mx-auto text-green-600" />
                  <p className="font-medium text-green-700 text-sm">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <Upload className="h-6 w-6 mx-auto text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Drop a PDF here or click to select
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Step 2: Parse button */}
          {file && (
            <Button
              variant={isParsed ? "outline" : "default"}
              onClick={handleParseFile}
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
                  {isParsed ? "Re-parse from file" : "2. Analyze PDF"}
                </>
              )}
            </Button>
          )}

          {/* Step 3: Editable fields (shown after parsing) */}
          {file && (
            <div className={`grid gap-3 ${!isParsed ? 'opacity-50' : ''}`}>
              <div className="grid grid-cols-4 items-center gap-2">
                <Label htmlFor="vendor" className="text-right text-sm">
                  Vendor:
                </Label>
                <Input
                  id="vendor"
                  value={vendor}
                  onChange={(e) => setVendor(e.target.value)}
                  className="col-span-3"
                  placeholder="Company name"
                  disabled={!isParsed}
                />
              </div>

              <div className="grid grid-cols-4 items-center gap-2">
                <Label htmlFor="date" className="text-right text-sm">
                  Date:
                </Label>
                <Input
                  id="date"
                  type="date"
                  value={invoiceDate}
                  onChange={(e) => setInvoiceDate(e.target.value)}
                  className="col-span-3"
                  disabled={!isParsed}
                />
              </div>

              <div className="grid grid-cols-4 items-center gap-2">
                <Label htmlFor="paymentType" className="text-right text-sm">
                  Type:
                </Label>
                <div className="col-span-3">
                  <Select
                    id="paymentType"
                    value={paymentType}
                    onChange={(e) => setPaymentType(e.target.value)}
                    options={PAYMENT_TYPES}
                    disabled={!isParsed}
                  />
                </div>
              </div>

              <div className="grid grid-cols-4 items-center gap-2">
                <Label className="text-right text-sm text-muted-foreground">
                  Amount:
                </Label>
                <span className="col-span-3 font-mono text-sm">
                  {amount || "-"}
                </span>
              </div>
            </div>
          )}

          {/* Preview new filename */}
          {isParsed && previewFilename && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm">
              <div className="font-medium text-green-700">New Filename</div>
              <div className="mt-1 font-mono text-green-800 truncate text-xs">
                {previewFilename}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!file || !invoiceDate || !isParsed || !vendor || isLoading}
          >
            {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            3. Upload Invoice
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
