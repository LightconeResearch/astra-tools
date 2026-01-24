import type { AnalysisSpec, Constraint, Decision } from '../types/asp';

/**
 * Analyzes and validates constraints between decision options.
 */
export class ConstraintGraph {
  private constraints: Constraint[] = [];
  private decisions: Record<string, Decision>;

  constructor(analysis: AnalysisSpec) {
    this.decisions = analysis.decisions || {};
    this.buildConstraints();
  }

  /**
   * Build the list of all constraints from the analysis.
   */
  private buildConstraints() {
    for (const [decisionId, decision] of Object.entries(this.decisions)) {
      for (const [optionId, option] of Object.entries(decision.options)) {
        const source = `${decisionId}.${optionId}`;

        // Add incompatible_with constraints
        if (option.incompatible_with) {
          for (const target of option.incompatible_with) {
            this.constraints.push({
              type: 'incompatible',
              source,
              target,
            });
          }
        }

        // Add requires constraints
        if (option.requires) {
          for (const target of option.requires) {
            this.constraints.push({
              type: 'requires',
              source,
              target,
            });
          }
        }
      }
    }
  }

  /**
   * Get all constraints.
   */
  getConstraints(): Constraint[] {
    return this.constraints;
  }

  /**
   * Get constraints for a specific decision/option.
   */
  getConstraintsFor(decisionId: string, optionId: string): Constraint[] {
    const ref = `${decisionId}.${optionId}`;
    return this.constraints.filter(c => c.source === ref || c.target === ref);
  }

  /**
   * Validate a set of selections against all constraints.
   * Returns list of violation messages.
   */
  validateSelections(selections: Record<string, string>): string[] {
    const violations: string[] = [];
    const selectedRefs = new Set<string>();

    // Build set of selected references
    for (const [decisionId, optionId] of Object.entries(selections)) {
      selectedRefs.add(`${decisionId}.${optionId}`);
    }

    for (const constraint of this.constraints) {
      const sourceSelected = selectedRefs.has(constraint.source);
      const targetSelected = selectedRefs.has(constraint.target);

      if (constraint.type === 'incompatible') {
        // Both cannot be selected at the same time
        if (sourceSelected && targetSelected) {
          violations.push(
            `Incompatible options selected: ${this.formatRef(constraint.source)} and ${this.formatRef(constraint.target)}`
          );
        }
      } else if (constraint.type === 'requires') {
        // If source is selected, target must also be selected
        if (sourceSelected && !targetSelected) {
          violations.push(
            `${this.formatRef(constraint.source)} requires ${this.formatRef(constraint.target)}`
          );
        }
      }
    }

    return violations;
  }

  /**
   * Get valid options for a decision given current selections.
   * Returns map of option_id -> { valid: boolean, reason?: string }
   */
  getValidOptions(
    decisionId: string,
    currentSelections: Record<string, string>
  ): Record<string, { valid: boolean; reason?: string }> {
    const decision = this.decisions[decisionId];
    if (!decision) {
      return {};
    }

    const result: Record<string, { valid: boolean; reason?: string }> = {};

    // Build set of currently selected refs (excluding this decision)
    const selectedRefs = new Set<string>();
    for (const [did, oid] of Object.entries(currentSelections)) {
      if (did !== decisionId) {
        selectedRefs.add(`${did}.${oid}`);
      }
    }

    for (const optionId of Object.keys(decision.options)) {
      const optionRef = `${decisionId}.${optionId}`;
      const validation = this.validateOptionAgainstSelections(optionRef, selectedRefs);
      result[optionId] = validation;
    }

    return result;
  }

  /**
   * Check if an option is valid given a set of selected references.
   */
  private validateOptionAgainstSelections(
    optionRef: string,
    selectedRefs: Set<string>
  ): { valid: boolean; reason?: string } {
    for (const constraint of this.constraints) {
      if (constraint.type === 'incompatible') {
        // Check if this option is incompatible with any selected option
        if (constraint.source === optionRef && selectedRefs.has(constraint.target)) {
          return {
            valid: false,
            reason: `Incompatible with ${this.formatRef(constraint.target)}`,
          };
        }
        if (constraint.target === optionRef && selectedRefs.has(constraint.source)) {
          return {
            valid: false,
            reason: `Incompatible with ${this.formatRef(constraint.source)}`,
          };
        }
      } else if (constraint.type === 'requires') {
        // Check if this option requires something that isn't selected
        if (constraint.source === optionRef && !selectedRefs.has(constraint.target)) {
          return {
            valid: false,
            reason: `Requires ${this.formatRef(constraint.target)}`,
          };
        }
      }
    }

    return { valid: true };
  }

  /**
   * Format a reference for display.
   */
  private formatRef(ref: string): string {
    const [decisionId, optionId] = ref.split('.');
    const decision = this.decisions[decisionId];
    const option = decision?.options[optionId];

    if (decision && option) {
      return `${decision.label} → ${option.label}`;
    }
    return ref;
  }

  /**
   * Get options that would become valid if a specific option is deselected.
   */
  getUnblockedOptions(
    decisionId: string,
    optionId: string,
    currentSelections: Record<string, string>
  ): string[] {
    const optionRef = `${decisionId}.${optionId}`;
    const unblocked: string[] = [];

    // Find all options that are blocked by this selection
    for (const constraint of this.constraints) {
      if (constraint.type === 'incompatible') {
        if (constraint.source === optionRef) {
          unblocked.push(constraint.target);
        } else if (constraint.target === optionRef) {
          unblocked.push(constraint.source);
        }
      }
    }

    return unblocked;
  }

  /**
   * Suggest fixes for constraint violations.
   */
  suggestFixes(selections: Record<string, string>): string[] {
    const violations = this.validateSelections(selections);
    const suggestions: string[] = [];

    // For each violation, suggest which option to change
    for (const violation of violations) {
      if (violation.includes('Incompatible')) {
        suggestions.push(
          `Consider changing one of the incompatible selections mentioned above`
        );
      } else if (violation.includes('requires')) {
        const match = violation.match(/requires (.+)$/);
        if (match) {
          suggestions.push(`Select the required option: ${match[1]}`);
        }
      }
    }

    return suggestions;
  }
}
