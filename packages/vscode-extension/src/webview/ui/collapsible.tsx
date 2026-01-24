import React, { useState, useCallback } from 'react';
import { cn } from '../lib/utils';
import { IconButton } from './button';

export interface CollapsibleProps {
  children: React.ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export function Collapsible({
  children,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  className,
}: CollapsibleProps): React.ReactElement {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);

  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen;

  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (controlledOpen === undefined) {
      setInternalOpen(newOpen);
    }
    onOpenChange?.(newOpen);
  }, [controlledOpen, onOpenChange]);

  return (
    <div className={className} data-state={isOpen ? 'open' : 'closed'}>
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          if (child.type === CollapsibleTrigger) {
            return React.cloneElement(child as React.ReactElement<CollapsibleTriggerProps>, {
              open: isOpen,
              onToggle: () => handleOpenChange(!isOpen),
            });
          }
          if (child.type === CollapsibleContent) {
            return React.cloneElement(child as React.ReactElement<CollapsibleContentProps>, {
              open: isOpen,
            });
          }
        }
        return child;
      })}
    </div>
  );
}

export interface CollapsibleTriggerProps {
  children: React.ReactNode;
  open?: boolean;
  onToggle?: () => void;
  className?: string;
  showIcon?: boolean;
}

export function CollapsibleTrigger({
  children,
  open,
  onToggle,
  className,
  showIcon = true,
}: CollapsibleTriggerProps): React.ReactElement {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {showIcon && (
        <IconButton
          aria-label={open ? 'Collapse' : 'Expand'}
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.();
          }}
          className="text-sm"
        >
          <span
            className={cn(
              'transition-transform duration-fast',
              open && 'rotate-90'
            )}
          >
            ▶
          </span>
        </IconButton>
      )}
      <div className="flex-1 min-w-0" onClick={onToggle}>
        {children}
      </div>
    </div>
  );
}

export interface CollapsibleContentProps {
  children: React.ReactNode;
  open?: boolean;
  className?: string;
}

export function CollapsibleContent({
  children,
  open,
  className,
}: CollapsibleContentProps): React.ReactElement | null {
  if (!open) return null;

  return (
    <div
      className={cn(
        'animate-slide-down overflow-hidden',
        className
      )}
    >
      {children}
    </div>
  );
}
