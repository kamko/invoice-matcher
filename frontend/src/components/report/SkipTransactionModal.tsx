import * as React from "react"
import { Loader2 } from "lucide-react"
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
import { formatCurrency } from "@/lib/utils"
import type { Transaction } from "@/api/client"

interface SkipTransactionModalProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (reason: string) => Promise<void>
  isLoading?: boolean
}

export function SkipTransactionModal({
  transaction,
  open,
  onOpenChange,
  onSubmit,
  isLoading,
}: SkipTransactionModalProps) {
  const [reason, setReason] = React.useState("")

  // Reset when modal closes
  React.useEffect(() => {
    if (!open) {
      setReason("")
    }
  }, [open])

  const handleSubmit = async () => {
    await onSubmit(reason)
  }

  if (!transaction) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle>Skip Transaction</DialogTitle>
          <DialogDescription>
            Skip this transaction for this month only. No rule will be created.
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
              <span className="truncate">{transaction.counter_name || transaction.counter_account || "-"}</span>
              <span>Note:</span>
              <span className="truncate">{transaction.note || "-"}</span>
            </div>
          </div>

          {/* Reason input */}
          <div className="space-y-2">
            <Label htmlFor="reason">Reason (optional)</Label>
            <Input
              id="reason"
              placeholder="e.g., Separate contract, handled manually..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Skip Transaction
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
