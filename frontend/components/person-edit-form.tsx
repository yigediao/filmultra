"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { buildApiUrl } from "@/lib/api";

type PersonEditFormProps = {
  personId: number;
  initialName: string;
};

export function PersonEditForm({ personId, initialName }: PersonEditFormProps) {
  const router = useRouter();
  const [name, setName] = useState(initialName);
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }

    setStatus("保存中…");
    const response = await fetch(buildApiUrl(`/api/people/${personId}`), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: name.trim() }),
    });

    if (!response.ok) {
      setStatus("更新失败");
      return;
    }

    setStatus("名称已更新");
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <form className="inline-form" onSubmit={(event) => void onSubmit(event)}>
      <input value={name} onChange={(event) => setName(event.target.value)} disabled={isPending} />
      <button type="submit" className="pill-button accent" disabled={isPending || !name.trim()}>
        Update Name
      </button>
      {status ? <span className="form-status">{status}</span> : null}
    </form>
  );
}
