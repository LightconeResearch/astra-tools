import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../lib/utils';

const radioVariants = cva(
  'relative flex-shrink-0 rounded-full border-2 transition-all duration-fast',
  {
    variants: {
      size: {
        sm: 'w-3 h-3',
        md: 'w-3.5 h-3.5',
        lg: 'w-4 h-4',
      },
      state: {
        unchecked: 'border-current bg-transparent',
        checked: 'border-current bg-current',
        disabled: 'border-muted bg-transparent opacity-50',
      },
    },
    defaultVariants: {
      size: 'md',
      state: 'unchecked',
    },
  }
);

export interface RadioIndicatorProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof radioVariants> {
  checked?: boolean;
  disabled?: boolean;
}

function getIndicatorState(checked?: boolean, disabled?: boolean): 'disabled' | 'checked' | 'unchecked' {
  if (disabled) return 'disabled';
  if (checked) return 'checked';
  return 'unchecked';
}

export const RadioIndicator = React.forwardRef<HTMLSpanElement, RadioIndicatorProps>(
  ({ className, size, checked, disabled, ...props }, ref) => {
    const state = getIndicatorState(checked, disabled);

    return (
      <span
        ref={ref}
        role="radio"
        aria-checked={checked}
        aria-disabled={disabled}
        className={cn(radioVariants({ size, state, className }))}
        {...props}
      >
        {checked && (
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-background" />
          </span>
        )}
      </span>
    );
  }
);
RadioIndicator.displayName = 'RadioIndicator';

// Checkbox variant (square with checkmark)
const checkboxVariants = cva(
  'relative flex-shrink-0 rounded-sm border-2 transition-all duration-fast flex items-center justify-center',
  {
    variants: {
      size: {
        sm: 'w-3 h-3',
        md: 'w-3.5 h-3.5',
        lg: 'w-4 h-4',
      },
      state: {
        unchecked: 'border-current bg-transparent',
        checked: 'border-accent bg-accent',
        disabled: 'border-muted bg-transparent opacity-50',
      },
    },
    defaultVariants: {
      size: 'md',
      state: 'unchecked',
    },
  }
);

export interface CheckboxIndicatorProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof checkboxVariants> {
  checked?: boolean;
  disabled?: boolean;
}

export const CheckboxIndicator = React.forwardRef<HTMLSpanElement, CheckboxIndicatorProps>(
  ({ className, size, checked, disabled, ...props }, ref) => {
    const state = getIndicatorState(checked, disabled);

    return (
      <span
        ref={ref}
        role="checkbox"
        aria-checked={checked}
        aria-disabled={disabled}
        className={cn(checkboxVariants({ size, state, className }))}
        {...props}
      >
        {checked && (
          <svg
            className="w-2.5 h-2.5 text-primary-foreground"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M2 5L4 7L8 3" />
          </svg>
        )}
      </span>
    );
  }
);
CheckboxIndicator.displayName = 'CheckboxIndicator';
