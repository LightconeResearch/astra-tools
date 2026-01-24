import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import type { AnalysisSpec, ValidationError } from '../types/asp';

export interface ParseResult {
  analysis: AnalysisSpec | null;
  errors: ValidationError[];
  raw?: string;
}

export interface ParsedAnalysis extends AnalysisSpec {
  _filePath: string;
}

/**
 * Parser for ASP analysis specification files (asp.yaml).
 */
export class AspParser {
  /**
   * Parse an ASP analysis file.
   */
  async parseFile(filePath: string): Promise<ParseResult> {
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      return this.parse(content, filePath);
    } catch (error) {
      return {
        analysis: null,
        errors: [
          {
            type: 'schema',
            message: `Failed to read file: ${error instanceof Error ? error.message : String(error)}`,
          },
        ],
      };
    }
  }

  /**
   * Parse ASP analysis from a YAML string.
   */
  parse(content: string, filePath?: string): ParseResult {
    const errors: ValidationError[] = [];

    try {
      const data = yaml.load(content) as AnalysisSpec;

      // Basic validation
      if (!data || typeof data !== 'object') {
        errors.push({
          type: 'schema',
          message: 'Invalid YAML: expected an object',
        });
        return { analysis: null, errors };
      }

      // Required fields validation
      if (!data.version) {
        errors.push({
          type: 'schema',
          message: 'Missing required field: version',
          path: 'version',
        });
      }

      if (!data.analysis) {
        errors.push({
          type: 'schema',
          message: 'Missing required field: analysis',
          path: 'analysis',
        });
      } else {
        if (!data.analysis.name) {
          errors.push({
            type: 'schema',
            message: 'Missing required field: analysis.name',
            path: 'analysis.name',
          });
        }
        if (!data.analysis.problem) {
          errors.push({
            type: 'schema',
            message: 'Missing required field: analysis.problem',
            path: 'analysis.problem',
          });
        }
      }

      // Semantic validation
      const semanticErrors = this.validateSemantics(data);
      errors.push(...semanticErrors);

      const analysis = filePath
        ? { ...data, _filePath: filePath }
        : data;

      return {
        analysis: errors.some(e => e.type === 'schema') ? null : analysis,
        errors,
        raw: content,
      };
    } catch (error) {
      if (error instanceof yaml.YAMLException) {
        errors.push({
          type: 'schema',
          message: `YAML parse error: ${error.message}`,
          line: error.mark?.line,
          column: error.mark?.column,
        });
      } else {
        errors.push({
          type: 'schema',
          message: `Parse error: ${error instanceof Error ? error.message : String(error)}`,
        });
      }
      return { analysis: null, errors };
    }
  }

  /**
   * Validate semantic rules that go beyond schema validation.
   */
  private validateSemantics(data: AnalysisSpec): ValidationError[] {
    const errors: ValidationError[] = [];

    if (!data.decisions) {
      return errors;
    }

    // Validate decision references in constraints
    for (const [decisionId, decision] of Object.entries(data.decisions)) {
      for (const [optionId, option] of Object.entries(decision.options)) {
        // Validate incompatible_with references
        if (option.incompatible_with) {
          for (const ref of option.incompatible_with) {
            const error = this.validateConstraintRef(ref, data.decisions, decisionId, optionId);
            if (error) errors.push(error);
          }
        }

        // Validate requires references
        if (option.requires) {
          for (const ref of option.requires) {
            const error = this.validateConstraintRef(ref, data.decisions, decisionId, optionId);
            if (error) errors.push(error);
          }
        }

        // Validate evidence references
        if (option.evidence) {
          for (const ev of option.evidence) {
            if (ev.insight && data.insights && !data.insights[ev.insight]) {
              errors.push({
                type: 'semantic',
                message: `Unknown insight reference: ${ev.insight}`,
                path: `decisions.${decisionId}.options.${optionId}.evidence`,
              });
            }
          }
        }
      }

      // Validate default option exists
      if (decision.default && !decision.options[decision.default]) {
        errors.push({
          type: 'semantic',
          message: `Default option '${decision.default}' not found in decision '${decisionId}'`,
          path: `decisions.${decisionId}.default`,
        });
      }
    }

    return errors;
  }

  /**
   * Validate a constraint reference (e.g., "model.svm").
   */
  private validateConstraintRef(
    ref: string,
    decisions: Record<string, { options: Record<string, unknown> }>,
    sourceDecision: string,
    sourceOption: string
  ): ValidationError | null {
    const parts = ref.split('.');
    if (parts.length !== 2) {
      return {
        type: 'semantic',
        message: `Invalid constraint reference format: ${ref} (expected 'decision.option')`,
        path: `decisions.${sourceDecision}.options.${sourceOption}`,
      };
    }

    const [decisionId, optionId] = parts;

    if (!decisions[decisionId]) {
      return {
        type: 'semantic',
        message: `Unknown decision in constraint: ${decisionId}`,
        path: `decisions.${sourceDecision}.options.${sourceOption}`,
      };
    }

    if (!decisions[decisionId].options[optionId]) {
      return {
        type: 'semantic',
        message: `Unknown option in constraint: ${ref}`,
        path: `decisions.${sourceDecision}.options.${sourceOption}`,
      };
    }

    // Check for self-reference
    if (decisionId === sourceDecision && optionId === sourceOption) {
      return {
        type: 'semantic',
        message: `Self-referencing constraint: ${ref}`,
        path: `decisions.${sourceDecision}.options.${sourceOption}`,
      };
    }

    return null;
  }

  /**
   * Get the default universe (all default options selected).
   */
  getDefaultUniverse(data: AnalysisSpec): Record<string, string> {
    const selections: Record<string, string> = {};

    if (!data.decisions) {
      return selections;
    }

    for (const [decisionId, decision] of Object.entries(data.decisions)) {
      if (decision.default) {
        selections[decisionId] = decision.default;
      } else {
        // Use first option if no default
        const firstOption = Object.keys(decision.options)[0];
        if (firstOption) {
          selections[decisionId] = firstOption;
        }
      }
    }

    return selections;
  }
}
