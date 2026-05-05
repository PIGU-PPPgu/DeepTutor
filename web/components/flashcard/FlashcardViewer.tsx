"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, Check, RotateCcw, X } from "lucide-react";
import type { Flashcard, FlashcardResult } from "@/lib/flashcard-types";

interface FlashcardViewerProps {
  result: FlashcardResult;
}

type Rating = "known" | "unknown";

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
  hard: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
};

const TYPE_LABELS: Record<string, string> = {
  concept: "Concept",
  formula: "Formula",
  true_false: "True/False",
  fill_blank: "Fill Blank",
};

function SingleCard({
  card,
  onRate,
}: {
  card: Flashcard;
  onRate: (rating: Rating) => void;
}) {
  const { t } = useTranslation();
  const [flipped, setFlipped] = useState(false);

  const diffClass = DIFFICULTY_COLORS[card.difficulty] ?? "bg-[var(--muted)] text-[var(--muted-foreground)]";
  const typeLabel = TYPE_LABELS[card.type] ?? card.type;

  return (
    <div className="flex flex-col gap-3">
      {/* Flip area */}
      <div
        className="relative cursor-pointer select-none"
        style={{ perspective: "900px" }}
        onClick={() => setFlipped((f) => !f)}
      >
        <div
          className="relative w-full transition-transform duration-500"
          style={{
            transformStyle: "preserve-3d",
            transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
            minHeight: "160px",
          }}
        >
          {/* Front */}
          <div
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--card)] p-5"
            style={{ backfaceVisibility: "hidden" }}
          >
            <div className="flex items-center gap-2 self-start">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${diffClass}`}>
                {card.difficulty}
              </span>
              <span className="rounded bg-[var(--muted)] px-1.5 py-0.5 text-[10px] text-[var(--muted-foreground)] uppercase tracking-wide">
                {typeLabel}
              </span>
            </div>
            <div className="text-center text-[15px] font-medium leading-relaxed text-[var(--foreground)]">
              {card.front}
            </div>
            <div className="mt-1 text-[11px] text-[var(--muted-foreground)]">
              {t("Tap to reveal answer")}
            </div>
          </div>

          {/* Back */}
          <div
            className="absolute inset-0 flex flex-col items-start gap-3 rounded-xl border border-[var(--primary)]/30 bg-[var(--primary)]/[0.04] p-5"
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
              {t("Answer")}
            </div>
            <div className="text-[14px] leading-relaxed text-[var(--foreground)]">{card.back}</div>
            {card.tags.length > 0 && (
              <div className="mt-auto flex flex-wrap gap-1">
                {card.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-[var(--border)] bg-[var(--muted)] px-2 py-0.5 text-[10px] text-[var(--muted-foreground)]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Rating buttons — shown after flip */}
      {flipped && (
        <div className="flex gap-2">
          <button
            onClick={() => onRate("unknown")}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-[13px] font-medium text-red-600 transition-colors hover:bg-red-100 dark:border-red-700/40 dark:bg-red-950/20 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            <X size={14} />
            {t("Need review")}
          </button>
          <button
            onClick={() => onRate("known")}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-[13px] font-medium text-green-700 transition-colors hover:bg-green-100 dark:border-green-700/40 dark:bg-green-950/20 dark:text-green-400 dark:hover:bg-green-950/40"
          >
            <Check size={14} />
            {t("Got it")}
          </button>
        </div>
      )}
    </div>
  );
}

export default function FlashcardViewer({ result }: FlashcardViewerProps) {
  const { t } = useTranslation();

  // deck = current set of cards being reviewed (may be a subset on retry)
  const [deck, setDeck] = useState<Flashcard[]>(result.cards);
  const [idx, setIdx] = useState(0);
  // ratings indexed by position within the current deck
  const [ratings, setRatings] = useState<Record<number, Rating>>({});
  const [done, setDone] = useState(false);

  const total = deck.length;
  const ratedCount = Object.keys(ratings).length;
  const knownCount = Object.values(ratings).filter((r) => r === "known").length;
  const unknownCount = ratedCount - knownCount;
  const progress = total > 0 ? Math.round((ratedCount / total) * 100) : 0;

  const handleRate = (rating: Rating) => {
    const newRatings = { ...ratings, [idx]: rating };
    setRatings(newRatings);
    if (idx < total - 1) {
      setIdx((i) => i + 1);
    } else {
      setDone(true);
    }
  };

  const handleReviewMissed = () => {
    const missed = deck.filter((_, i) => ratings[i] === "unknown");
    if (missed.length === 0) return;
    setDeck(missed);
    setIdx(0);
    setRatings({});
    setDone(false);
  };

  const handleRestartAll = () => {
    setDeck(result.cards);
    setIdx(0);
    setRatings({});
    setDone(false);
  };

  const card = deck[idx] ?? null;

  /* ---- Completion screen ---- */
  if (done || (!card && ratedCount > 0)) {
    const percentage = total > 0 ? Math.round((knownCount / total) * 100) : 0;
    const missedCards = deck.filter((_, i) => ratings[i] === "unknown");
    return (
      <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)]">
        <div className="border-b border-[var(--border)] px-4 py-2.5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            {t("Flashcards — Session Complete")}
          </div>
        </div>
        <div className="flex flex-col items-center gap-4 px-6 py-6">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--primary)]/10">
            <Check size={28} className="text-[var(--primary)]" />
          </div>
          <div className="text-center">
            <div className="text-lg font-semibold text-[var(--foreground)]">
              {percentage}% {t("Known")}
            </div>
            <div className="mt-1 text-sm text-[var(--muted-foreground)]">
              {knownCount} {t("got it")} · {unknownCount} {t("need review")} · {total} {t("total")}
            </div>
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            {missedCards.length > 0 && (
              <button
                onClick={handleReviewMissed}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-[13px] font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]"
              >
                <RotateCcw size={13} />
                {t("Review {{n}} missed", { n: missedCards.length })}
              </button>
            )}
            <button
              onClick={handleRestartAll}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-[13px] font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]"
            >
              <RotateCcw size={13} />
              {t("Restart all")}
            </button>
            <a
              href="/chat?capability=deep_question"
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-2 text-[13px] font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90"
            >
              {t("Take Quiz")}
              <ArrowRight size={13} />
            </a>
          </div>

          {result.intervals_days.length > 0 && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 px-4 py-3 text-center">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                {t("Ebbinghaus Review Schedule")}
              </div>
              <div className="text-xs text-[var(--muted-foreground)]">
                {t("Review again in")} {result.intervals_days.join(", ")} {t("days")}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!card) return null;

  /* ---- Active card ---- */
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-2.5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
          {t("Flashcards")} · {total} {t("cards")}
        </div>
        <span className="text-[11px] text-[var(--muted-foreground)]">
          {idx + 1} / {total}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 w-full bg-[var(--muted)]">
        <div
          className="h-full bg-[var(--primary)] transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Card */}
      <div className="p-4">
        <SingleCard key={`${deck === result.cards ? "all" : "missed"}-${idx}`} card={card} onRate={handleRate} />
      </div>

      {/* Dot navigation */}
      <div className="flex items-center justify-between border-t border-[var(--border)] px-4 py-2">
        <button
          disabled={idx === 0}
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
          className="text-[12px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] disabled:opacity-30"
        >
          ← {t("Prev")}
        </button>
        <div className="flex gap-1">
          {deck.map((_, i) => (
            <button
              key={i}
              onClick={() => setIdx(i)}
              className={`rounded-full transition-all ${
                i === idx
                  ? "h-1.5 w-3 bg-[var(--primary)]"
                  : ratings[i] === "known"
                    ? "h-1.5 w-1.5 bg-green-500"
                    : ratings[i] === "unknown"
                      ? "h-1.5 w-1.5 bg-red-400"
                      : "h-1.5 w-1.5 bg-[var(--border)]"
              }`}
            />
          ))}
        </div>
        <button
          disabled={idx === total - 1}
          onClick={() => setIdx((i) => Math.min(total - 1, i + 1))}
          className="text-[12px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] disabled:opacity-30"
        >
          {t("Next")} →
        </button>
      </div>
    </div>
  );
}
