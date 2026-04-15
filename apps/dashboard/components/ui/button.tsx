import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[calc(var(--radius)-0.45rem)] text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 ring-offset-background",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-primary-foreground shadow-[var(--shadow-button)] hover:bg-[color:var(--primary-strong)]",
        accent:
          "bg-accent text-accent-foreground shadow-[var(--shadow-button)] hover:bg-[color:var(--accent-strong)]",
        outline:
          "border border-border/70 bg-card/70 text-foreground hover:bg-card",
        ghost:
          "bg-transparent text-foreground hover:bg-muted/70",
        subtle:
          "bg-white/55 text-foreground shadow-[var(--shadow-soft)] hover:bg-white/75",
      },
      size: {
        sm: "h-9 px-3.5",
        default: "h-10 px-4.5",
        lg: "h-11 px-5.5",
        icon: "size-10",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
