import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Folder } from "lucide-react"

interface InvoiceDirInputProps {
  invoiceDir: string
  onInvoiceDirChange: (dir: string) => void
  onNext: () => void
  onBack?: () => void
}

export function InvoiceDirInput({
  invoiceDir,
  onInvoiceDirChange,
  onNext,
  onBack,
}: InvoiceDirInputProps) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="invoice-dir">Invoice Directory</Label>
        <div className="relative">
          <Folder className="absolute left-3 top-2.5 h-5 w-5 text-muted-foreground" />
          <Input
            id="invoice-dir"
            type="text"
            value={invoiceDir}
            onChange={(e) => onInvoiceDirChange(e.target.value)}
            placeholder="e.g., C:\invoices or /home/user/invoices"
            className="pl-10"
          />
        </div>
        <p className="text-sm text-muted-foreground">
          Enter the path to your local directory containing invoice PDFs.
          Leave empty to skip invoice matching.
        </p>
      </div>

      <div className="flex justify-between">
        {onBack && (
          <Button type="button" variant="outline" onClick={onBack}>
            Back
          </Button>
        )}
        <Button
          type="button"
          onClick={onNext}
          className={onBack ? "" : "ml-auto"}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
