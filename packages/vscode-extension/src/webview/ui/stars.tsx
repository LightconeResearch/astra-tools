import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../lib/utils';

const starsVariants = cva('inline-flex gap-0.5', {
  variants: {
    size: {
      sm: 'text-xs',
      md: 'text-sm',
      lg: 'text-base',
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export interface StarsProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof starsVariants> {
  /** Number of filled stars (1-5) */
  filled: number;
  /** Total number of stars to display */
  total?: number;
  /** Custom filled star character */
  filledChar?: string;
  /** Custom empty star character */
  emptyChar?: string;
}

export function Stars({
  filled,
  total = 5,
  size,
  filledChar = '★',
  emptyChar = '★',
  className,
  ...props
}: StarsProps): React.ReactElement {
  const clampedFilled = Math.max(0, Math.min(filled, total));

  return (
    <span
      className={cn(starsVariants({ size, className }))}
      role="img"
      aria-label={`${clampedFilled} out of ${total} stars`}
      {...props}
    >
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={cn(
            'text-chart-yellow transition-opacity duration-fast',
            i < clampedFilled ? 'opacity-100' : 'opacity-30'
          )}
        >
          {i < clampedFilled ? filledChar : emptyChar}
        </span>
      ))}
    </span>
  );
}

// Importance stars: converts importance level (1=critical, 5=detail) to filled stars
export interface ImportanceStarsProps
  extends Omit<StarsProps, 'filled'> {
  /** Importance level (1 = most important = 5 stars, 5 = least important = 1 star) */
  importance: number;
}

export function ImportanceStars({ importance, ...props }: ImportanceStarsProps): React.ReactElement {
  // importance 1 = 5 stars, importance 5 = 1 star
  const filled = Math.max(1, Math.min(5, 6 - importance));

  return (
    <Stars
      filled={filled}
      title={`Importance: ${importance} (1=critical, 5=detail)`}
      {...props}
    />
  );
}
