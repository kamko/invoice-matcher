import * as React from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Eye, EyeOff } from "lucide-react"

interface FioTokenInputProps {
  token: string
  onTokenChange: (token: string) => void
  onNext: () => void
  onBack: () => void
}

export function FioTokenInput({
  token,
  onTokenChange,
  onNext,
  onBack,
}: FioTokenInputProps) {
  const [showToken, setShowToken] = React.useState(false)

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="fio-token">Fio Bank API Token</Label>
        <div className="relative">
          <Input
            id="fio-token"
            type={showToken ? "text" : "password"}
            value={token}
            onChange={(e) => onTokenChange(e.target.value)}
            placeholder="Enter your Fio Bank API token"
            className="pr-10"
          />
          <button
            type="button"
            className="absolute right-3 top-2.5 text-muted-foreground hover:text-foreground"
            onClick={() => setShowToken(!showToken)}
          >
            {showToken ? (
              <EyeOff className="h-5 w-5" />
            ) : (
              <Eye className="h-5 w-5" />
            )}
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          Your token is used only for this session and is not stored.
          You can get your token from Fio Bank internet banking settings.
        </p>
      </div>

      <div className="flex justify-between">
        <Button type="button" variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button
          type="button"
          onClick={onNext}
          disabled={!token.trim()}
        >
          Start Reconciliation
        </Button>
      </div>
    </div>
  )
}
