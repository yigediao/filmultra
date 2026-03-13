"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { buildApiUrl } from "@/lib/api";
import { PersonListItem } from "@/lib/types";

type MergePeopleFormProps = {
  currentPersonId: number;
  people: PersonListItem[];
};

export function MergePeopleForm({ currentPersonId, people }: MergePeopleFormProps) {
  const router = useRouter();
  const candidates = useMemo(
    () => people.filter((person) => person.id !== currentPersonId),
    [people, currentPersonId],
  );
  const [selectedId, setSelectedId] = useState<string>(candidates[0] ? String(candidates[0].id) : "");
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setSelectedId(candidates[0] ? String(candidates[0].id) : "");
  }, [currentPersonId, candidates]);

  async function mergeSelected() {
    if (!selectedId) {
      return;
    }

    setStatus("合并中…");
    const response = await fetch(buildApiUrl("/api/people/merge"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        target_person_id: currentPersonId,
        source_person_ids: [Number(selectedId)],
      }),
    });

    if (!response.ok) {
      setStatus("合并失败");
      return;
    }

    setStatus("已合并");
    startTransition(() => {
      router.refresh();
    });
  }

  if (candidates.length === 0) {
    return <p className="muted-copy">当前没有其他已命名人物可合并。</p>;
  }

  return (
    <div className="stack-form">
      <label className="field-label" htmlFor="merge-person-select">
        将其他人物并入当前人物
      </label>
      <div className="inline-form">
        <select
          id="merge-person-select"
          value={selectedId}
          onChange={(event) => setSelectedId(event.target.value)}
          disabled={isPending}
        >
          {candidates.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name} · {person.face_count} faces
            </option>
          ))}
        </select>
        <button type="button" className="pill-button accent" onClick={() => void mergeSelected()} disabled={isPending || !selectedId}>
          Merge Into Current
        </button>
      </div>
      {status ? <span className="form-status">{status}</span> : null}
    </div>
  );
}
