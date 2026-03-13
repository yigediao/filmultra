"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { getJob, triggerFaceDetect, triggerRecluster } from "@/lib/api";
import { JobRead } from "@/lib/types";

type JobAction = "detect" | "recluster" | null;

export function FaceJobsPanel() {
  const router = useRouter();
  const [action, setAction] = useState<JobAction>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [message, setMessage] = useState<string>("人物识别现在会先入队，再在后台执行。");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (jobId === null || action === null) {
      return;
    }

    const activeJobId = jobId;
    const activeAction = action;
    let cancelled = false;

    async function poll() {
      while (!cancelled) {
        try {
          const job = await getJob(activeJobId);
          if (cancelled) {
            return;
          }

          if (job.status === "pending") {
            setMessage(`任务 #${job.id} 已入队，正在等待后台执行。`);
          } else if (job.status === "running") {
            setMessage(`任务 #${job.id} 正在后台处理中，你可以继续浏览页面。`);
          } else if (job.status === "completed") {
            setMessage(formatCompletedMessage(job, activeAction));
            startTransition(() => {
              router.refresh();
            });
            setAction(null);
            setJobId(null);
            return;
          } else {
            setMessage(`任务 #${job.id} 失败：${job.error_message ?? "请检查后端日志。"}`);
            setAction(null);
            setJobId(null);
            return;
          }
        } catch {
          setMessage("无法获取任务状态，请检查后端是否仍在运行。");
          setAction(null);
          setJobId(null);
          return;
        }

        await new Promise((resolve) => {
          window.setTimeout(resolve, 1500);
        });
      }
    }

    void poll();

    return () => {
      cancelled = true;
    };
  }, [action, jobId, router, startTransition]);

  async function run(nextAction: JobAction) {
    setAction(nextAction);
    setMessage(nextAction === "detect" ? "正在把人物检测任务加入后台队列…" : "正在把重聚类任务加入后台队列…");

    try {
      const job = nextAction === "detect" ? await triggerFaceDetect() : await triggerRecluster();
      setJobId(job.id);
      setMessage(`任务 #${job.id} 已入队，后台处理中。`);
    } catch {
      setMessage("任务创建失败，请检查后端是否可用。");
      setAction(null);
    }
  }

  return (
    <div className="face-job-panel">
      <div>
        <p className="eyebrow">Face Jobs</p>
        <h2>人物识别</h2>
        <p className="muted-copy">{message}</p>
      </div>
      <div className="job-actions">
        <button
          type="button"
          className="pill-button accent"
          onClick={() => void run("detect")}
          disabled={isPending || action !== null || jobId !== null}
        >
          {action === "detect" ? "Queued…" : "Detect Faces"}
        </button>
        <button
          type="button"
          className="pill-button"
          onClick={() => void run("recluster")}
          disabled={isPending || action !== null || jobId !== null}
        >
          {action === "recluster" ? "Queued…" : "Recluster"}
        </button>
      </div>
    </div>
  );
}

function formatCompletedMessage(job: JobRead, action: Exclude<JobAction, null>): string {
  if (action === "detect") {
    const processedAssets = Number(job.result_json?.processed_assets ?? 0);
    const detectedFaces = Number(job.result_json?.detected_faces ?? 0);
    return `人物检测完成：处理了 ${processedAssets} 张资产，识别到 ${detectedFaces} 张脸。`;
  }

  const namedPeople = Number(job.result_json?.named_people ?? 0);
  const unnamedClusters = Number(job.result_json?.unnamed_clusters ?? 0);
  return `重聚类完成：当前 ${namedPeople} 个已命名人物，${unnamedClusters} 个未命名聚类。`;
}
