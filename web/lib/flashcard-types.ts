/**
 * Shared types for Flashcard generation (flashcard capability).
 */

export type FlashcardType = "concept" | "formula" | "true_false" | "fill_blank";
export type FlashcardDifficulty = "easy" | "medium" | "hard";

export interface Flashcard {
  id: number;
  type: FlashcardType;
  front: string;
  back: string;
  tags: string[];
  difficulty: FlashcardDifficulty;
}

export interface FlashcardResult {
  cards: Flashcard[];
  review_schedule: Record<string, number[]>;
  intervals_days: number[];
}

export interface FlashcardFormConfig {
  subject: string;
  chapter: string;
}

export const DEFAULT_FLASHCARD_CONFIG: FlashcardFormConfig = {
  subject: "",
  chapter: "",
};

/**
 * Extract FlashcardResult from the raw `result` event metadata returned by
 * the flashcard capability.
 */
export function extractFlashcardResult(
  resultMetadata: Record<string, unknown> | undefined,
): FlashcardResult | null {
  if (!resultMetadata) return null;
  const cards = resultMetadata.cards as Flashcard[] | undefined;
  if (!Array.isArray(cards) || cards.length === 0) return null;
  return {
    cards,
    review_schedule: (resultMetadata.review_schedule as Record<string, number[]>) ?? {},
    intervals_days: (resultMetadata.intervals_days as number[]) ?? [],
  };
}

/**
 * Build the `config` payload for a flashcard WebSocket request.
 */
export function buildFlashcardWSConfig(cfg: FlashcardFormConfig): Record<string, unknown> {
  return {
    subject: cfg.subject.trim() || "通用",
    chapter: cfg.chapter.trim(),
  };
}
