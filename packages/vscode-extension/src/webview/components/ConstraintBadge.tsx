import React from 'react';
import { Badge, Tooltip, cn } from '../ui';

interface ConstraintBadgeProps {
  count: number;
  violations?: string[];
}

export function ConstraintBadge({ count, violations = [] }: ConstraintBadgeProps): React.ReactElement {
  const hasViolations = violations.length > 0;

  const badge = (
    <Badge
      variant={hasViolations ? 'error' : 'warning'}
      className={cn('cursor-help', hasViolations && 'animate-pulse')}
    >
      {hasViolations ? '⚠' : '🔗'} {count}
    </Badge>
  );

  const tooltipContent = hasViolations ? (
    <div>
      <div className="font-semibold text-error mb-1">
        Constraint Violations:
      </div>
      <ul className="list-disc list-inside space-y-0.5">
        {violations.map((v, i) => (
          <li key={i}>{v}</li>
        ))}
      </ul>
    </div>
  ) : (
    <span>{count} constraint{count !== 1 ? 's' : ''} defined</span>
  );

  return (
    <Tooltip content={tooltipContent} side="bottom" align="end">
      {badge}
    </Tooltip>
  );
}
