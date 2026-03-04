import * as React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface Step {
  id: string
  title: string
  description?: string
}

interface WizardLayoutProps {
  steps: Step[]
  currentStep: number
  children: React.ReactNode
}

export function WizardLayout({ steps, currentStep, children }: WizardLayoutProps) {
  return (
    <div className="max-w-2xl mx-auto">
      {/* Step indicator */}
      <div className="mb-8">
        <nav aria-label="Progress">
          <ol className="flex items-center">
            {steps.map((step, index) => (
              <li
                key={step.id}
                className={cn(
                  "relative",
                  index !== steps.length - 1 ? "pr-8 sm:pr-20 flex-1" : ""
                )}
              >
                <div className="flex items-center">
                  <div
                    className={cn(
                      "relative flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium",
                      index < currentStep
                        ? "bg-primary text-primary-foreground"
                        : index === currentStep
                        ? "border-2 border-primary text-primary"
                        : "border-2 border-muted text-muted-foreground"
                    )}
                  >
                    {index < currentStep ? (
                      <svg
                        className="h-5 w-5"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    ) : (
                      index + 1
                    )}
                  </div>
                  {index !== steps.length - 1 && (
                    <div
                      className={cn(
                        "absolute top-4 left-8 -ml-px h-0.5 w-full sm:w-20",
                        index < currentStep ? "bg-primary" : "bg-muted"
                      )}
                    />
                  )}
                </div>
                <div className="mt-2">
                  <span
                    className={cn(
                      "text-sm font-medium",
                      index <= currentStep
                        ? "text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    {step.title}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        </nav>
      </div>

      {/* Step content */}
      <Card>
        <CardHeader>
          <CardTitle>{steps[currentStep]?.title}</CardTitle>
          {steps[currentStep]?.description && (
            <p className="text-sm text-muted-foreground">
              {steps[currentStep].description}
            </p>
          )}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  )
}
