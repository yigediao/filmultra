"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { getPreviewUrl, reviewPersonCandidate } from "@/lib/api";
import { PersonReviewCandidate } from "@/lib/types";

type ReviewCandidateCardProps = {
  personId: number;
  candidate: PersonReviewCandidate;
  targetPerson?: {
    id: number;
    name: string;
  };
};

function percent(value: number | null) {
  if (value === null) {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

export function ReviewCandidateCard({ personId, candidate, targetPerson }: ReviewCandidateCardProps) {
  const router = useRouter();
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const previewUrl = getPreviewUrl(candidate.face.preview_url);
  const currentAssignment =
    candidate.current_assignment_name && candidate.current_assignment_name !== targetPerson?.name
      ? candidate.current_assignment_name
      : null;

  async function run(action: "confirm" | "reject" | "skip") {
    setStatus(action === "confirm" ? "确认中…" : action === "reject" ? "标记中…" : "跳过中…");
    try {
      await reviewPersonCandidate(personId, {
        face_id: candidate.face.id,
        action,
      });
      setStatus(action === "confirm" ? "已确认" : action === "reject" ? "已排除" : "已跳过");
      startTransition(() => {
        router.refresh();
      });
    } catch {
      setStatus("更新失败");
    }
  }

  return (
    <article className="review-candidate-card">
      {previewUrl ? <img src={previewUrl} alt={candidate.face.person_name ?? "candidate"} className="face-review-thumb" /> : null}
      <div className="review-candidate-body">
        {targetPerson ? (
          <div className="review-target">
            <span className="stat-label">Target Person</span>
            <Link href={`/people/${targetPerson.id}`} className="review-target-link">
              {targetPerson.name}
            </Link>
          </div>
        ) : null}
        <div className="face-review-header">
          <strong>{targetPerson?.name ?? "待确认候选"}</strong>
          <span>{candidate.auto_assign_eligible ? "High" : "Needs Review"}</span>
        </div>
        {currentAssignment ? <p className="muted-copy">当前归类: {currentAssignment}</p> : null}
        <p className="muted-copy">
          Asset:{" "}
          <Link href={`/assets/${candidate.face.logical_asset_id}`}>
            {candidate.face.asset_display_name ?? `#${candidate.face.logical_asset_id}`}
          </Link>
        </p>
        <div className="review-metrics">
          <span>Decision {percent(candidate.decision_score)}</span>
          <span>Centroid {percent(candidate.centroid_similarity)}</span>
          <span>Prototype {percent(candidate.prototype_similarity)}</span>
          <span>Nearest {percent(candidate.exemplar_similarity)}</span>
          <span>Uncertainty {percent(candidate.uncertainty)}</span>
          <span>Ambiguity {percent(candidate.ambiguity)}</span>
          {candidate.negative_similarity !== null ? <span>Negative Risk {percent(candidate.negative_similarity)}</span> : null}
          {candidate.competitor_person_name ? <span>Runner-up {candidate.competitor_person_name} {percent(candidate.competitor_score)}</span> : null}
        </div>
        <div className="job-actions">
          <button type="button" className="pill-button accent" onClick={() => void run("confirm")} disabled={isPending}>
            Yes, It's Them
          </button>
          <button type="button" className="pill-button" onClick={() => void run("reject")} disabled={isPending}>
            Not This Person
          </button>
          <button type="button" className="pill-button" onClick={() => void run("skip")} disabled={isPending}>
            Skip
          </button>
        </div>
        {status ? <span className="form-status">{status}</span> : null}
      </div>
    </article>
  );
}
