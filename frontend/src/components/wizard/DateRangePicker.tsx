import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"

interface DateRangePickerProps {
  fromDate: string
  toDate: string
  onFromDateChange: (date: string) => void
  onToDateChange: (date: string) => void
  onNext: () => void
  onBack?: () => void
}

// Format date as YYYY-MM-DD using local time (not UTC)
function formatLocalDate(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function DateRangePicker({
  fromDate,
  toDate,
  onFromDateChange,
  onToDateChange,
  onNext,
  onBack,
}: DateRangePickerProps) {
  const isValid = fromDate && toDate && fromDate <= toDate

  // Quick presets
  const setThisMonth = () => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), 1)
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
    onFromDateChange(formatLocalDate(start))
    onToDateChange(formatLocalDate(end))
  }

  const setLastMonth = () => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    const end = new Date(now.getFullYear(), now.getMonth(), 0)
    onFromDateChange(formatLocalDate(start))
    onToDateChange(formatLocalDate(end))
  }

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={setThisMonth}>
          This Month
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={setLastMonth}>
          Last Month
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="from-date">From Date</Label>
          <Input
            id="from-date"
            type="date"
            value={fromDate}
            onChange={(e) => onFromDateChange(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="to-date">To Date</Label>
          <Input
            id="to-date"
            type="date"
            value={toDate}
            onChange={(e) => onToDateChange(e.target.value)}
          />
        </div>
      </div>

      {fromDate && toDate && fromDate > toDate && (
        <p className="text-sm text-destructive">
          From date must be before or equal to To date
        </p>
      )}

      <div className="flex justify-between">
        {onBack && (
          <Button type="button" variant="outline" onClick={onBack}>
            Back
          </Button>
        )}
        <Button
          type="button"
          onClick={onNext}
          disabled={!isValid}
          className={onBack ? "" : "ml-auto"}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
