import React, { useState, useRef, useEffect } from 'react';
import { cn } from '../lib/utils';

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  style?: React.CSSProperties;
  multiline?: boolean;
}

export function MarkdownEditor({
  value,
  onChange,
  className,
  style,
  multiline = false,
}: MarkdownEditorProps): React.ReactElement {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!isEditing) return;
    const element = multiline ? textareaRef.current : inputRef.current;
    if (element) {
      element.focus();
      element.select();
    }
  }, [isEditing, multiline]);

  useEffect(() => {
    setEditValue(value);
  }, [value]);

  function handleClick(e: React.MouseEvent): void {
    e.stopPropagation();
    setIsEditing(true);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>): void {
    const newValue = e.target.value;
    setEditValue(newValue);

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      if (newValue !== value) {
        onChange(newValue);
      }
    }, 500);
  }

  function handleBlur(): void {
    setIsEditing(false);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    if (editValue !== value) {
      onChange(editValue);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent): void {
    if (e.key === 'Escape') {
      setEditValue(value);
      setIsEditing(false);
    } else if (e.key === 'Enter' && !multiline) {
      e.preventDefault();
      inputRef.current?.blur();
    }
  }

  function stopPropagation(e: React.MouseEvent): void {
    e.stopPropagation();
  }

  const inputClassName = cn(
    'w-full px-1 py-0.5 bg-input text-input-foreground border border-input-border rounded focus:outline-none focus:border-accent',
    multiline && 'min-h-[60px] resize-y',
    className
  );

  if (isEditing) {
    if (multiline) {
      return (
        <textarea
          ref={textareaRef}
          className={inputClassName}
          value={editValue}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          style={style}
          onClick={stopPropagation}
        />
      );
    }
    return (
      <input
        ref={inputRef}
        className={inputClassName}
        value={editValue}
        onChange={handleChange}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        style={style}
        onClick={stopPropagation}
      />
    );
  }

  return (
    <span
      className={cn('editable-text', className)}
      onClick={handleClick}
      style={style}
      title="Click to edit"
    >
      {value || <span className="opacity-50 italic">Click to edit</span>}
    </span>
  );
}
