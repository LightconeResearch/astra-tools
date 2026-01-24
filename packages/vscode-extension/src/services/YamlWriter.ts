import * as fs from 'fs/promises';

/**
 * Round-trip YAML editor that preserves comments and formatting.
 *
 * This implementation uses string manipulation to update specific values
 * while preserving the original formatting, comments, and structure.
 */
export class YamlWriter {
  /**
   * Update a field in a YAML file while preserving formatting.
   */
  async updateField(filePath: string, path: string[], value: string): Promise<void> {
    const content = await fs.readFile(filePath, 'utf-8');
    const updated = this.updateFieldInContent(content, path, value);
    await fs.writeFile(filePath, updated, 'utf-8');
  }

  /**
   * Update a field in YAML content.
   */
  updateFieldInContent(content: string, path: string[], newValue: string): string {
    const lines = content.split('\n');
    const result = this.findAndUpdateField(lines, path, 0, 0, newValue);

    if (result.found) {
      return result.lines.join('\n');
    }

    throw new Error(`Field not found: ${path.join('.')}`);
  }

  /**
   * Find and update a field in the YAML lines.
   */
  private findAndUpdateField(
    lines: string[],
    path: string[],
    pathIndex: number,
    startLine: number,
    newValue: string
  ): { found: boolean; lines: string[] } {
    if (pathIndex >= path.length) {
      return { found: false, lines };
    }

    const targetKey = path[pathIndex];
    const isLastKey = pathIndex === path.length - 1;
    let currentIndent = -1;
    let inTargetBlock = false;
    let targetBlockIndent = 0;

    for (let i = startLine; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trimStart();

      // Skip empty lines and comments
      if (trimmed === '' || trimmed.startsWith('#')) {
        continue;
      }

      // Calculate indentation
      const indent = line.length - trimmed.length;

      // If we're tracking a block and encounter less indentation, we've exited
      if (inTargetBlock && indent <= targetBlockIndent) {
        return { found: false, lines };
      }

      // Check if this line starts with the target key
      const keyMatch = trimmed.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*:/);
      if (keyMatch) {
        const key = keyMatch[0].slice(0, -1).trim();

        // Track the base indentation level
        if (currentIndent === -1) {
          currentIndent = indent;
        }

        // Only consider keys at the current indentation level
        if (indent === currentIndent && key === targetKey) {
          if (isLastKey) {
            // This is the field we want to update
            const updatedLine = this.updateValueInLine(line, newValue);
            const newLines = [...lines];
            newLines[i] = updatedLine;
            return { found: true, lines: newLines };
          } else {
            // Need to go deeper into this block
            inTargetBlock = true;
            targetBlockIndent = indent;

            // Find the next line with content and use that as the new base indent
            for (let j = i + 1; j < lines.length; j++) {
              const nextTrimmed = lines[j].trimStart();
              if (nextTrimmed !== '' && !nextTrimmed.startsWith('#')) {
                return this.findAndUpdateField(
                  lines,
                  path,
                  pathIndex + 1,
                  j,
                  newValue
                );
              }
            }
          }
        }
      }
    }

    return { found: false, lines };
  }

  /**
   * Update the value portion of a YAML line.
   */
  private updateValueInLine(line: string, newValue: string): string {
    // Match key: value pattern
    const match = line.match(/^(\s*)([a-zA-Z_][a-zA-Z0-9_]*\s*:)\s*(.*)?$/);
    if (!match) {
      return line;
    }

    const [, indent, keyPart, existingValue] = match;

    // Check if the existing value is a multi-line string indicator
    if (existingValue?.trim() === '|' || existingValue?.trim() === '>') {
      // For multi-line strings, we need more complex handling
      // For now, just update to inline if the new value is simple
      if (!newValue.includes('\n')) {
        return `${indent}${keyPart} "${this.escapeYamlString(newValue)}"`;
      }
    }

    // Preserve inline comments
    const commentMatch = existingValue?.match(/\s+(#.*)$/);
    const comment = commentMatch ? commentMatch[1] : '';

    // Determine if we need quotes
    const needsQuotes = this.needsQuotes(newValue);
    const formattedValue = needsQuotes
      ? `"${this.escapeYamlString(newValue)}"`
      : newValue;

    return `${indent}${keyPart} ${formattedValue}${comment ? ' ' + comment : ''}`;
  }

  /**
   * Check if a string value needs to be quoted in YAML.
   */
  private needsQuotes(value: string): boolean {
    // Needs quotes if:
    // - Contains special characters
    // - Looks like a number, boolean, or null
    // - Contains leading/trailing whitespace
    // - Contains colons or other YAML special chars

    if (value !== value.trim()) return true;
    if (/^[0-9.-]+$/.test(value)) return true;
    if (['true', 'false', 'null', 'yes', 'no', 'on', 'off'].includes(value.toLowerCase())) return true;
    if (/[:#\[\]{}|>&*!?]/.test(value)) return true;
    if (value === '') return true;

    return false;
  }

  /**
   * Escape special characters in a YAML string.
   */
  private escapeYamlString(value: string): string {
    return value
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n')
      .replace(/\t/g, '\\t');
  }

  /**
   * Create a new field in a YAML file.
   */
  async addField(
    filePath: string,
    parentPath: string[],
    key: string,
    value: unknown
  ): Promise<void> {
    const content = await fs.readFile(filePath, 'utf-8');
    const lines = content.split('\n');

    // Find the parent block
    let insertLine = -1;
    let insertIndent = 0;

    // For now, just append to the end of the file
    // A more sophisticated implementation would find the correct location
    const yaml = await import('js-yaml');
    const newContent = yaml.dump({ [key]: value }, { lineWidth: 100 });

    const updated = content + '\n' + newContent;
    await fs.writeFile(filePath, updated, 'utf-8');
  }

  /**
   * Delete a field from a YAML file.
   */
  async deleteField(filePath: string, path: string[]): Promise<void> {
    const content = await fs.readFile(filePath, 'utf-8');
    const lines = content.split('\n');

    // Find and remove the field and any nested content
    // This is a simplified implementation
    // A full implementation would need to handle nested blocks properly

    const targetKey = path[path.length - 1];
    const newLines: string[] = [];
    let skipUntilIndent = -1;

    for (const line of lines) {
      const trimmed = line.trimStart();
      const indent = line.length - trimmed.length;

      if (skipUntilIndent >= 0) {
        if (indent <= skipUntilIndent && trimmed !== '' && !trimmed.startsWith('#')) {
          skipUntilIndent = -1;
        } else {
          continue;
        }
      }

      const keyMatch = trimmed.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*:/);
      if (keyMatch && keyMatch[1] === targetKey) {
        skipUntilIndent = indent;
        continue;
      }

      newLines.push(line);
    }

    await fs.writeFile(filePath, newLines.join('\n'), 'utf-8');
  }
}
