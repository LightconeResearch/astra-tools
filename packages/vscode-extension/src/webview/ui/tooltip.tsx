import React, { useState, useCallback } from 'react';
import { cn } from '../lib/utils';

export interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactElement;
  side?: 'top' | 'bottom' | 'left' | 'right';
  align?: 'start' | 'center' | 'end';
  delayMs?: number;
  className?: string;
}

export function Tooltip({
  content,
  children,
  side = 'top',
  align = 'center',
  delayMs = 200,
  className,
}: TooltipProps): React.ReactElement {
  const [isVisible, setIsVisible] = useState(false);
  const [timeoutId, setTimeoutId] = useState<ReturnType<typeof setTimeout> | null>(null);

  const showTooltip = useCallback(() => {
    const id = setTimeout(() => setIsVisible(true), delayMs);
    setTimeoutId(id);
  }, [delayMs]);

  const hideTooltip = useCallback(() => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      setTimeoutId(null);
    }
    setIsVisible(false);
  }, [timeoutId]);

  const positionClasses: Record<typeof side, string> = {
    top: 'bottom-full mb-1',
    bottom: 'top-full mt-1',
    left: 'right-full mr-1',
    right: 'left-full ml-1',
  };

  const isVertical = side === 'top' || side === 'bottom';
  const alignClasses: Record<typeof align, string> = {
    start: isVertical ? 'left-0' : 'top-0',
    center: isVertical ? 'left-1/2 -translate-x-1/2' : 'top-1/2 -translate-y-1/2',
    end: isVertical ? 'right-0' : 'bottom-0',
  };

  return (
    <div className="relative inline-block">
      {React.cloneElement(children, {
        onMouseEnter: (e: React.MouseEvent) => {
          showTooltip();
          children.props.onMouseEnter?.(e);
        },
        onMouseLeave: (e: React.MouseEvent) => {
          hideTooltip();
          children.props.onMouseLeave?.(e);
        },
        onFocus: (e: React.FocusEvent) => {
          showTooltip();
          children.props.onFocus?.(e);
        },
        onBlur: (e: React.FocusEvent) => {
          hideTooltip();
          children.props.onBlur?.(e);
        },
      })}
      {isVisible && content && (
        <div
          role="tooltip"
          className={cn(
            'absolute z-50 px-2 py-1.5 text-sm',
            'bg-tooltip text-tooltip-foreground border border-tooltip-border',
            'rounded shadow-tooltip',
            'animate-fade-in whitespace-nowrap',
            positionClasses[side],
            alignClasses[align],
            className
          )}
        >
          {content}
        </div>
      )}
    </div>
  );
}

// Simple inline tooltip for constraint warnings
export interface InlineWarningProps {
  message: string;
  className?: string;
}

export function InlineWarning({ message, className }: InlineWarningProps): React.ReactElement {
  return (
    <Tooltip content={message} side="top">
      <span
        className={cn(
          'inline-flex items-center justify-center w-4 h-4',
          'rounded-full bg-warning-background text-warning',
          'text-xs font-bold cursor-help',
          className
        )}
      >
        !
      </span>
    </Tooltip>
  );
}
