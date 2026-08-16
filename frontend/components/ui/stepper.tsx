import { cn } from "@/lib/utils";

export interface StepperStep {
  label: string;
}

interface StepperProps {
  steps: StepperStep[];
  currentIndex: number;
  className?: string;
}

// Minimal, purpose-built for the Adaptive ERP Company Setup Wizard --
// gated (no jump-ahead) linear progress, not a general-purpose tabs
// replacement. Deliberately plain (no @base-ui primitive) since it has no
// interactive behavior of its own beyond reflecting `currentIndex`.
export function Stepper({ steps, currentIndex, className }: StepperProps) {
  return (
    <ol className={cn("flex flex-wrap items-center gap-x-2 gap-y-3", className)}>
      {steps.map((step, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "upcoming";
        return (
          <li key={step.label} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                state === "done" && "bg-primary text-primary-foreground",
                state === "current" && "border-2 border-primary text-primary",
                state === "upcoming" && "border border-border text-muted-foreground"
              )}
            >
              {state === "done" ? "✓" : index + 1}
            </span>
            <span
              className={cn(
                "text-xs whitespace-nowrap",
                state === "current" ? "font-medium text-foreground" : "text-muted-foreground"
              )}
            >
              {step.label}
            </span>
            {index < steps.length - 1 && <span className="mx-1 h-px w-4 bg-border" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}
