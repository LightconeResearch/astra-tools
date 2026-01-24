/**
 * TypeScript types for ASP (Agentic Science Protocol) analysis specifications.
 * Derived from the JSON schema at spec/draft/analysis.schema.json
 */

export type DecisionType = 'data' | 'method' | 'parameter';
export type InputType = 'data' | 'analysis' | 'literature';
export type OutputType = 'metric' | 'figure' | 'table' | 'data' | 'model' | 'report';
export type OutputDtype = 'float' | 'int' | 'bool' | 'string';

export interface Evidence {
  insight?: string;
  ref?: string;
  finding?: string;
}

export interface Option {
  label: string;
  description?: string;
  value?: unknown;
  evidence?: Evidence[];
  incompatible_with?: string[];
  requires?: string[];
}

export interface Decision {
  label: string;
  type: DecisionType;
  importance?: number;
  rationale?: string;
  default?: string;
  options: Record<string, Option>;
}

export interface Input {
  id: string;
  type: InputType;
  source?: string | Source;
  ref?: string;
  version?: string;
  use_outputs?: string[];
  description?: string;
}

export interface Source {
  type: 'url' | 's3' | 'sklearn' | 'asp' | 'file';
  url?: string;
  bucket?: string;
  key?: string;
  version_id?: string;
  region?: string;
  dataset?: string;
  analysis?: string;
  version?: string;
  output?: string;
  execution?: string;
  path?: string;
  checksum?: {
    algorithm: 'sha256' | 'sha512' | 'md5';
    value: string;
  };
}

export interface Output {
  id: string;
  type: OutputType;
  dtype?: OutputDtype;
  range?: [number, number];
  formats?: string[];
  primary?: boolean;
  description?: string;
}

export interface AnalysisContent {
  name: string;
  description?: string;
  authors?: string[];
  tags?: string[];
  problem: string;
  inputs: Input[];
  outputs: Output[];
}

export interface PaperSource {
  doi: string;
}

export interface AnalysisSource {
  analysis: string;
  version?: string;
  universe?: string;
}

export interface FigureEvidence {
  figure: string;
  caption?: string;
}

export interface QuoteEvidence {
  quote: string;
  location?: string;
}

export interface TableEvidence {
  table: string;
  location?: string;
  value?: string;
}

export interface EquationEvidence {
  equation: string;
  expression?: string;
}

export interface ResultEvidence {
  result: string;
  location?: string;
  value?: unknown;
}

export interface MetricEvidence {
  metric: string;
  value: unknown;
}

export interface OutputEvidence {
  output: string;
}

export type InsightEvidence =
  | FigureEvidence
  | QuoteEvidence
  | TableEvidence
  | EquationEvidence
  | ResultEvidence
  | MetricEvidence
  | OutputEvidence;

export interface Insight {
  claim: string;
  source: PaperSource | AnalysisSource;
  evidence: InsightEvidence[];
  scope?: string;
}

export interface AnalysisSpec {
  $schema?: string;
  version: string;
  analysis: AnalysisContent;
  decisions?: Record<string, Decision>;
  insights?: Record<string, Insight>;
}

// Constraint representation for the constraint graph
export interface Constraint {
  type: 'incompatible' | 'requires';
  source: string; // "decision.option" format
  target: string; // "decision.option" format
}

// Selection tracking for universes
export interface Universe {
  name: string;
  selections: Record<string, string>; // decision_id -> option_id
}

// Validation error types
export interface ValidationError {
  type: 'schema' | 'semantic';
  message: string;
  path?: string;
  line?: number;
  column?: number;
}
