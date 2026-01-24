import React from 'react';
import type { Decision } from '../../types/asp';
import { useAspStore } from '../stores/aspStore';
import { OptionCard } from './OptionCard';
import { ConstraintBadge } from './ConstraintBadge';
import { MarkdownEditor } from './MarkdownEditor';
import {
  Card,
  CardHeader,
  CardContent,
  TypeBadge,
  ImportanceStars,
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
  cn,
} from '../ui';

interface DecisionBoxProps {
  decisionId: string;
  decision: Decision;
}

export function DecisionBox({ decisionId, decision }: DecisionBoxProps): React.ReactElement {
  const { selection, expandedDecisions, constraints, setSelection, toggleExpanded, sendMessage } =
    useAspStore();

  const isSelected =
    selection?.type === 'decision' && selection.decisionId === decisionId;
  const isExpanded = expandedDecisions.has(decisionId);

  // Get constraints for this decision
  const decisionConstraints = constraints.filter((c) => {
    const [sourceDecision] = c.source.split('.');
    const [targetDecision] = c.target.split('.');
    return sourceDecision === decisionId || targetDecision === decisionId;
  });

  const handleClick = () => {
    setSelection({ type: 'decision', decisionId });
  };

  const handleLabelChange = (newValue: string) => {
    sendMessage({
      type: 'updateField',
      path: ['decisions', decisionId, 'label'],
      value: newValue,
    });
  };

  const handleRationaleChange = (newValue: string) => {
    sendMessage({
      type: 'updateField',
      path: ['decisions', decisionId, 'rationale'],
      value: newValue,
    });
  };

  return (
    <Card
      variant={isSelected ? 'selected' : 'interactive'}
      className="mb-3"
      onClick={handleClick}
    >
      <Collapsible open={isExpanded} onOpenChange={() => toggleExpanded(decisionId)}>
        {/* Header row */}
        <CardHeader size={isExpanded ? 'md' : 'sm'}>
          <CollapsibleTrigger open={isExpanded} onToggle={() => toggleExpanded(decisionId)}>
            <div className="flex items-center gap-2 flex-1 min-w-0">
              {/* Label */}
              <MarkdownEditor
                value={decision.label}
                onChange={handleLabelChange}
                className="font-semibold text-lg flex-1"
              />

              {/* Type badge */}
              <TypeBadge type={decision.type} />

              {/* Importance stars */}
              <ImportanceStars importance={decision.importance || 3} />

              {/* Constraint count */}
              {decisionConstraints.length > 0 && (
                <ConstraintBadge count={decisionConstraints.length} />
              )}
            </div>
          </CollapsibleTrigger>
        </CardHeader>

        {/* Rationale (always visible) */}
        {decision.rationale && (
          <div className="text-sm text-muted italic mb-3">
            <MarkdownEditor
              value={decision.rationale}
              onChange={handleRationaleChange}
            />
          </div>
        )}

        {/* Options grid */}
        <CardContent>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
            {Object.entries(decision.options).map(([optionId, option]) => (
              <OptionCard
                key={optionId}
                decisionId={decisionId}
                optionId={optionId}
                option={option}
                isDefault={decision.default === optionId}
                isExpanded={isExpanded}
              />
            ))}
          </div>
        </CardContent>

        {/* Expanded constraint details */}
        <CollapsibleContent open={isExpanded}>
          {decisionConstraints.length > 0 && (
            <div className="mt-3 pt-3 border-t border-card-border text-sm">
              <div className="font-semibold mb-1">Constraints:</div>
              <ul className={cn(
                "list-disc list-inside space-y-0.5",
                "text-muted"
              )}>
                {decisionConstraints.map((c, i) => (
                  <li key={i}>
                    <span className="text-muted/70">{c.type}:</span>{' '}
                    <span className="font-mono text-xs">{c.source}</span>
                    {' ↔ '}
                    <span className="font-mono text-xs">{c.target}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
