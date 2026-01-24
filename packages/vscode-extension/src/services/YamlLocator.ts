import * as fs from 'fs/promises';

interface Location {
  startLine: number;
  endLine: number;
  startColumn: number;
  endColumn: number;
}

/**
 * Finds the line locations of elements in a YAML file.
 * Used to select the relevant portion of asp.yaml when user clicks
 * on elements in the visualization, so Claude Code can see the selection.
 */
export class YamlLocator {
  private content: string = '';
  private lines: string[] = [];

  async loadFile(filePath: string): Promise<void> {
    this.content = await fs.readFile(filePath, 'utf-8');
    this.lines = this.content.split('\n');
  }

  /**
   * Find the location of a decision in the YAML file.
   */
  findDecision(decisionId: string): Location | null {
    // Look for "  decisionId:" pattern under "decisions:"
    const decisionsStart = this.findLineStartingWith('decisions:');
    if (decisionsStart === -1) return null;

    // Find the decision key
    const decisionPattern = new RegExp(`^  ${decisionId}:`);
    let decisionStart = -1;

    for (let i = decisionsStart + 1; i < this.lines.length; i++) {
      const line = this.lines[i];

      // If we hit a non-indented line (except empty), we've left decisions section
      if (line.trim() !== '' && !line.startsWith(' ')) {
        break;
      }

      if (decisionPattern.test(line)) {
        decisionStart = i;
        break;
      }
    }

    if (decisionStart === -1) return null;

    // Find the end of this decision block (next sibling or end of decisions)
    const decisionEnd = this.findBlockEnd(decisionStart, 2);

    return {
      startLine: decisionStart,
      endLine: decisionEnd,
      startColumn: 0,
      endColumn: this.lines[decisionEnd]?.length || 0,
    };
  }

  /**
   * Find the location of an option within a decision.
   */
  findOption(decisionId: string, optionId: string): Location | null {
    const decision = this.findDecision(decisionId);
    if (!decision) return null;

    // Find "options:" within this decision
    let optionsStart = -1;
    for (let i = decision.startLine; i <= decision.endLine; i++) {
      if (this.lines[i].match(/^\s{4}options:/)) {
        optionsStart = i;
        break;
      }
    }

    if (optionsStart === -1) return null;

    // Find the specific option
    const optionPattern = new RegExp(`^\\s{6}${optionId}:`);
    let optionStart = -1;

    for (let i = optionsStart + 1; i <= decision.endLine; i++) {
      if (optionPattern.test(this.lines[i])) {
        optionStart = i;
        break;
      }
    }

    if (optionStart === -1) return null;

    // Find the end of this option block
    const optionEnd = this.findBlockEnd(optionStart, 6);

    return {
      startLine: optionStart,
      endLine: Math.min(optionEnd, decision.endLine),
      startColumn: 0,
      endColumn: this.lines[Math.min(optionEnd, decision.endLine)]?.length || 0,
    };
  }

  /**
   * Find the location of the analysis section.
   */
  findAnalysis(): Location | null {
    const analysisStart = this.findLineStartingWith('analysis:');
    if (analysisStart === -1) return null;

    const analysisEnd = this.findBlockEnd(analysisStart, 0);

    return {
      startLine: analysisStart,
      endLine: analysisEnd,
      startColumn: 0,
      endColumn: this.lines[analysisEnd]?.length || 0,
    };
  }

  /**
   * Find the location of an input.
   */
  findInput(inputId: string): Location | null {
    // Find inputs section within analysis
    const inputsStart = this.findLineMatching(/^\s{2}inputs:/);
    if (inputsStart === -1) return null;

    // Find the input with matching id
    for (let i = inputsStart + 1; i < this.lines.length; i++) {
      const line = this.lines[i];

      // Check for "- id: inputId" pattern
      if (line.match(new RegExp(`^\\s{4}- id: ${inputId}\\s*$`))) {
        const inputEnd = this.findArrayItemEnd(i, 4);
        return {
          startLine: i,
          endLine: inputEnd,
          startColumn: 0,
          endColumn: this.lines[inputEnd]?.length || 0,
        };
      }

      // If we've left the inputs section
      if (line.trim() !== '' && !line.startsWith('    ') && !line.startsWith('  inputs:')) {
        if (!line.startsWith('      ')) break;
      }
    }

    return null;
  }

  /**
   * Find the location of an output.
   */
  findOutput(outputId: string): Location | null {
    // Find outputs section within analysis
    const outputsStart = this.findLineMatching(/^\s{2}outputs:/);
    if (outputsStart === -1) return null;

    // Find the output with matching id
    for (let i = outputsStart + 1; i < this.lines.length; i++) {
      const line = this.lines[i];

      if (line.match(new RegExp(`^\\s{4}- id: ${outputId}\\s*$`))) {
        const outputEnd = this.findArrayItemEnd(i, 4);
        return {
          startLine: i,
          endLine: outputEnd,
          startColumn: 0,
          endColumn: this.lines[outputEnd]?.length || 0,
        };
      }

      if (line.trim() !== '' && !line.startsWith('    ') && !line.startsWith('  outputs:')) {
        if (!line.startsWith('      ')) break;
      }
    }

    return null;
  }

  private findLineStartingWith(prefix: string): number {
    for (let i = 0; i < this.lines.length; i++) {
      if (this.lines[i].startsWith(prefix)) {
        return i;
      }
    }
    return -1;
  }

  private findLineMatching(pattern: RegExp): number {
    for (let i = 0; i < this.lines.length; i++) {
      if (pattern.test(this.lines[i])) {
        return i;
      }
    }
    return -1;
  }

  /**
   * Find the end of a YAML block starting at startLine with given indentation.
   */
  private findBlockEnd(startLine: number, indent: number): number {
    const indentStr = ' '.repeat(indent);
    let lastContentLine = startLine;

    for (let i = startLine + 1; i < this.lines.length; i++) {
      const line = this.lines[i];

      // Empty line - continue
      if (line.trim() === '') {
        continue;
      }

      // Comment at same or deeper indent - include it
      if (line.trimStart().startsWith('#') && line.startsWith(indentStr)) {
        lastContentLine = i;
        continue;
      }

      // Line with less or equal indent (but not empty) - we've exited the block
      const lineIndent = line.length - line.trimStart().length;
      if (lineIndent <= indent && line.trim() !== '') {
        break;
      }

      // Content line with deeper indent - include it
      lastContentLine = i;
    }

    return lastContentLine;
  }

  /**
   * Find the end of a YAML array item.
   */
  private findArrayItemEnd(startLine: number, baseIndent: number): number {
    let lastContentLine = startLine;

    for (let i = startLine + 1; i < this.lines.length; i++) {
      const line = this.lines[i];

      if (line.trim() === '') continue;

      const lineIndent = line.length - line.trimStart().length;

      // Next array item or less indent means we're done
      if (line.match(/^\s*- /) && lineIndent <= baseIndent) break;
      if (lineIndent <= baseIndent && !line.match(/^\s*- /)) break;

      lastContentLine = i;
    }

    return lastContentLine;
  }
}
