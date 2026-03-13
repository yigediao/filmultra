"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { buildApiUrl } from "@/lib/api";

type RatingControlProps = {
  assetId: number;
  rating: number;
  onRatingChange?: (rating: number) => void;
};

export function RatingControl({ assetId, rating, onRatingChange }: RatingControlProps) {
  const router = useRouter();
  const [currentRating, setCurrentRating] = useState(rating);
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function updateRating(nextRating: number) {
    const previousRating = currentRating;
    setCurrentRating(nextRating);
    onRatingChange?.(nextRating);
    setStatus("保存中…");

    const response = await fetch(buildApiUrl(`/api/assets/${assetId}/rating`), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ rating: nextRating }),
    });

    if (!response.ok) {
      setCurrentRating(previousRating);
      onRatingChange?.(previousRating);
      setStatus("保存失败");
      return;
    }
    setStatus(`已设为 ${nextRating} 星`);

    startTransition(() => {
      router.refresh();
    });
  }

  useEffect(() => {
    setCurrentRating(rating);
    onRatingChange?.(rating);
  }, [onRatingChange, rating]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }
      const target = event.target;
      if (target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        return;
      }
      if (!["0", "1", "2", "3", "4", "5"].includes(event.key) || isPending) {
        return;
      }
      event.preventDefault();
      void updateRating(Number(event.key));
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isPending, currentRating]);

  return (
    <div className="rating-control-shell">
      <div className="rating-control">
        {Array.from({ length: 5 }, (_, index) => {
          const starValue = index + 1;
          const active = currentRating >= starValue;
          return (
            <button
              key={starValue}
              type="button"
              className={`rating-star ${active ? "active" : ""}`}
              onClick={() => void updateRating(starValue)}
              disabled={isPending}
              aria-label={`Set rating to ${starValue}`}
            >
              ★
            </button>
          );
        })}
        <button
          type="button"
          className="rating-reset"
          onClick={() => void updateRating(0)}
          disabled={isPending}
        >
          Clear
        </button>
      </div>
      <span className="form-status">数字键 `0-5` 也能快速评分{status ? ` · ${status}` : ""}</span>
    </div>
  );
}
