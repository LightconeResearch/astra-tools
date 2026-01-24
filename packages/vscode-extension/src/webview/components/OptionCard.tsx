import React from 'react';
import type { Option } from '../../types/asp';
import { useAspStore } from '../stores/aspStore';
import { MarkdownEditor } from './MarkdownEditor';
import {
  Card,
  RadioIndicator,
  Badge,
  Tooltip,
  cn,
} from '../ui';

interface OptionCardProps {
  decisionId: string;
  optionId: string;
  option: Option;
  isDefault: boolean;
  isExpanded: boolean;
}

export function OptionCard({
  decisionId,
  optionId,
  option,
  isDefault,
  isExpanded,
}: OptionCardProps): React.ReactElement {
  const { selection, currentSelections, validOptions, setSelection, updateSelection, sendMessage } =
    useAspStore();

  const isSelected =
    selection?.type === 'option' &&
    selection.decisionId === decisionId &&
    selection.optionId === optionId;

  const isCurrentlySelected = currentSelections[decisionId] === optionId;

  // Check validity based on constraints
  const validity = validOptions[decisionId]?.[optionId] ?? { valid: true };
  const isValid = validity.valid;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelection({ type: 'option', decisionId, optionId });
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isValid) {
      updateSelection(decisionId, optionId);
    }
  };

  const handleLabelChange = (newValue: string) => {
    sendMessage({
      type: 'updateField',
      path: ['decisions', decisionId, 'options', optionId, 'label'],
      value: newValue,
    });
  };

  const handleDescriptionChange = (newValue: string) => {
    sendMessage({
      type: 'updateField',
      path: ['decisions', decisionId, 'options', optionId, 'description'],
      value: newValue,
    });
  };

  const constraints = [
    ...(option.incompatible_with?.map((ref) => ({ type: 'incompatible' as const, ref })) || []),
    ...(option.requires?.map((ref) => ({ type: 'requires' as const, ref })) || []),
  ];

  const cardContent = (
    <Card
      variant={isSelected ? 'selected' : 'default'}
      padding="sm"
      className={cn(
        'flex items-start gap-2 cursor-pointer transition-all',
        'hover:bg-list-hover',
        isDefault && 'border-chart-blue',
        !isValid && 'opacity-50 cursor-not-allowed hover:bg-transparent'
      )}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      {/* Selection indicator */}
      <RadioIndicator
        checked={isCurrentlySelected}
        disabled={!isValid}
        className="mt-0.5"
      />

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Label row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <MarkdownEditor
            value={option.label}
            onChange={handleLabelChange}
            className="font-medium"
          />
          {isDefault && (
            <Badge variant="outline" size="sm" className="text-muted uppercase tracking-wider">
              default
            </Badge>
          )}
        </div>

        {/* Description when expanded */}
        {isExpanded && option.description && (
          <div className="mt-1 text-xs text-muted">
            <MarkdownEditor
              value={option.description}
              onChange={handleDescriptionChange}
            />
          </div>
        )}

        {/* Constraint indicators when expanded */}
        {constraints.length > 0 && isExpanded && (
          <div className="mt-1.5 flex gap-1 flex-wrap">
            {constraints.map((c, i) => (
              <Badge
                key={i}
                variant={c.type === 'incompatible' ? 'warning' : 'info'}
                size="sm"
              >
                {c.type === 'incompatible' ? '⚠' : '→'} {c.ref}
              </Badge>
            ))}
          </div>
        )}

        {/* Evidence count */}
        {option.evidence && option.evidence.length > 0 && (
          <div className="mt-1 text-xs text-muted">
            📚 {option.evidence.length} evidence
          </div>
        )}
      </div>
    </Card>
  );

  // Wrap with tooltip if invalid
  if (!isValid && validity.reason) {
    return (
      <Tooltip content={validity.reason} side="top">
        {cardContent}
      </Tooltip>
    );
  }

  return cardContent;
}
