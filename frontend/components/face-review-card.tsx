"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { buildApiUrl, getPreviewUrl } from "@/lib/api";
import { Face, PersonListItem } from "@/lib/types";

type FaceReviewCardProps = {
  face: Face;
  people: PersonListItem[];
};

export function FaceReviewCard({ face, people }: FaceReviewCardProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const assignablePeople = useMemo(
    () => people.filter((person) => person.id !== face.person_id),
    [people, face.person_id],
  );
  const [selectedId, setSelectedId] = useState<string>(assignablePeople[0] ? String(assignablePeople[0].id) : "");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    setSelectedId(assignablePeople[0] ? String(assignablePeople[0].id) : "");
  }, [assignablePeople]);

  async function run(action: "assign_person" | "unassign" | "restore_auto") {
    setStatus("保存中…");

    const payload =
      action === "assign_person"
        ? { action, person_id: Number(selectedId) }
        : { action };

    const response = await fetch(buildApiUrl(`/api/faces/${face.id}/assignment`), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      setStatus("更新失败");
      return;
    }

    setStatus("已更新");
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <article className="face-review-card">
      {face.preview_url ? (
        <img
          src={getPreviewUrl(face.preview_url) ?? undefined}
          alt={face.person_name ?? face.cluster_id ?? "face"}
          className="face-review-thumb"
        />
      ) : null}
      <div className="face-review-body">
        <div className="face-review-header">
          <strong>{face.person_name ?? face.cluster_id ?? "Unassigned"}</strong>
          <span>{face.assignment_locked ? "Manual" : "Auto"}</span>
        </div>
        <p className="muted-copy">
          Asset:{" "}
          <Link href={`/assets/${face.logical_asset_id}`}>
            {face.asset_display_name ?? `#${face.logical_asset_id}`}
          </Link>
        </p>
        <div className="inline-form">
          <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={isPending || assignablePeople.length === 0}>
            {assignablePeople.length === 0 ? (
              <option value="">No other people</option>
            ) : (
              assignablePeople.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))
            )}
          </select>
          <button
            type="button"
            className="pill-button accent"
            onClick={() => void run("assign_person")}
            disabled={isPending || !selectedId}
          >
            Move
          </button>
          <button type="button" className="pill-button" onClick={() => void run("unassign")} disabled={isPending}>
            Remove
          </button>
          {face.assignment_locked ? (
            <button type="button" className="pill-button" onClick={() => void run("restore_auto")} disabled={isPending}>
              Restore Auto
            </button>
          ) : null}
        </div>
        {status ? <span className="form-status">{status}</span> : null}
      </div>
    </article>
  );
}
