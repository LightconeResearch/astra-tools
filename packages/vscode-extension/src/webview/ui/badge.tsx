import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium rounded-sm transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-badge text-badge-foreground',
        method: 'bg-chart-purple text-white',
        parameter: 'bg-chart-blue text-white',
        data: 'bg-chart-green text-white',
        warning: 'bg-warning-background text-warning',
        error: 'bg-error-background text-error',
        info: 'bg-info-background text-info',
        success: 'bg-success/20 text-success',
        outline: 'border border-border bg-transparent',
      },
      size: {
        sm: 'text-[10px] px-1 py-0',
        md: 'text-xs px-1.5 py-0.5',
        lg: 'text-sm px-2 py-1',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, size, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(badgeVariants({ variant, size, className }))}
      {...props}
    />
  )
);
Badge.displayName = 'Badge';

// Convenience component for type badges that auto-maps decision types
export interface TypeBadgeProps extends Omit<BadgeProps, 'variant'> {
  type: 'method' | 'parameter' | 'data' | string;
}

const TYPE_VARIANT_MAP: Record<string, BadgeProps['variant']> = {
  method: 'method',
  parameter: 'parameter',
  data: 'data',
};

export function TypeBadge({ type, className, ...props }: TypeBadgeProps): React.ReactElement {
  const variant = TYPE_VARIANT_MAP[type] ?? 'default';

  return (
    <Badge
      variant={variant}
      className={cn('uppercase tracking-wide', className)}
      {...props}
    >
      {type}
    </Badge>
  );
}
