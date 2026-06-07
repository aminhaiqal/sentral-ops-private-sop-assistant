export type BoundaryWarning = {
  category: string;
  message: string;
};

export type SourceSnippet = {
  document_id: string;
  title: string;
  chunk_id: string;
  score: number;
  excerpt: string;
};

export type AskResponse = {
  answer: string;
  sources: SourceSnippet[];
  warnings: BoundaryWarning[];
};

export type DemoQuestion = {
  question: string;
  boundary_expected: boolean;
};

export type HealthResponse = {
  status: string;
  app_name: string;
  qdrant_collection: string;
  openai_configured: boolean;
};

export type IngestResponse = {
  documents: number;
  chunks: number;
  collection: string;
};
