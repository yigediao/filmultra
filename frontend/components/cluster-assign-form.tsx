"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { buildApiUrl } from "@/lib/api";

type ClusterAssignFormProps = {
  clusterId: string;
};

export function ClusterAssignForm({ clusterId }: ClusterAssignFormProps) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }

    setStatus("保存中…");
    const response = await fetch(buildApiUrl("/api/people"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: name.trim(),
        cluster_id: clusterId,
      }),
    });

    if (!response.ok) {
      setStatus("归类失败");
      return;
    }

    setStatus("已归入人物");
    setName("");
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <form className="inline-form" onSubmit={(event) => void onSubmit(event)}>
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="输入人物名称"
        disabled={isPending}
      />
      <button type="submit" className="pill-button accent" disabled={isPending || !name.trim()}>
        Name Cluster
      </button>
      {status ? <span className="form-status">{status}</span> : null}
    </form>
  );
}
