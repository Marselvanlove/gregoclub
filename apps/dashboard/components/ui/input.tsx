import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-11 w-full rounded-[calc(var(--radius)-0.5rem)] border border-border/70 bg-white/70 px-3.5 text-sm text-foreground shadow-[var(--shadow-soft)] transition placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
