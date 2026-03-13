"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { BodyBboxEditor } from "@/components/body-bbox-editor";
import { BodyMaskEditor } from "@/components/body-mask-editor";
import { ObjectGlbViewer } from "@/components/object-glb-viewer";
import { getJob, getPreviewUrl, previewObjectMask, triggerSam3dObject } from "@/lib/api";
import { BodyMaskEditStroke, ObjectReconstruction, ObjectReconstructionPreview } from "@/lib/types";

type ObjectReconstructionPanelProps = {
  assetId: number;
  heroPreviewUrl: string | null;
  reconstructions: ObjectReconstruction[];
};

export function ObjectReconstructionPanel({
  assetId,
  heroPreviewUrl,
  reconstructions,
}: ObjectReconstructionPanelProps) {
  const router = useRouter();
  const [jobId, setJobId] = useState<number | null>(null);
  const [message, setMessage] = useState("先框住目标物体，再预览并微调 SAM2 mask。");
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [objectBbox, setObjectBbox] = useState<number[] | null>(null);
  const [previewResult, setPreviewResult] = useState<ObjectReconstructionPreview | null>(null);
  const [selectedMaskIndex, setSelectedMaskIndex] = useState<number | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [maskEdits, setMaskEdits] = useState<BodyMaskEditStroke[]>([]);
  const [maskBrushMode, setMaskBrushMode] = useState<"add" | "erase">("add");
  const [maskBrushRadius, setMaskBrushRadius] = useState(28);
  const [, startTransition] = useTransition();
  const sourcePreviewUrl = previewResult
    ? getPreviewUrl(previewResult.source_image_url)
    : heroPreviewUrl
      ? getPreviewUrl(heroPreviewUrl)
      : null;

  useEffect(() => {
    if (jobId === null) {
      return;
    }

    const activeJobId = jobId;
    let cancelled = false;
    async function poll() {
      while (!cancelled) {
        try {
          const job = await getJob(activeJobId);
          if (cancelled) {
            return;
          }

          if (job.status === "pending") {
            setMessage(`任务 #${job.id} 已入队，等待后台开始。`);
          } else if (job.status === "running") {
            setMessage(`任务 #${job.id} 正在后台执行 SAM2 / SAM 3D Objects。`);
          } else if (job.status === "completed") {
            setMessage("对象 3D 任务已完成。");
            startTransition(() => {
              router.refresh();
            });
            setJobId(null);
            return;
          } else {
            setMessage(`任务 #${job.id} 失败：${job.error_message ?? "请检查后端日志。"}`);
            setJobId(null);
            return;
          }
        } catch {
          setMessage("无法获取对象 3D 任务状态，请检查后端服务。");
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
  }, [jobId, router, startTransition]);

  useEffect(() => {
    if (sourcePreviewUrl && objectBbox === null) {
      setObjectBbox([120, 120, 920, 1320]);
    }
  }, [objectBbox, sourcePreviewUrl]);

  useEffect(() => {
    if (imageSize === null) {
      return;
    }
    setObjectBbox((current) => {
      if (current === null) {
        return defaultObjectBbox(imageSize);
      }
      return [
        round2(clamp(current[0], 0, imageSize.width - 1)),
        round2(clamp(current[1], 0, imageSize.height - 1)),
        round2(clamp(current[2], Math.min(current[0] + 40, imageSize.width), imageSize.width)),
        round2(clamp(current[3], Math.min(current[1] + 40, imageSize.height), imageSize.height)),
      ];
    });
  }, [imageSize]);

  useEffect(() => {
    setMaskEdits([]);
  }, [previewResult?.preview_id, selectedMaskIndex]);

  async function runPreview() {
    if (objectBbox === null) {
      return;
    }

    setIsPreviewLoading(true);
    setMessage("正在预览对象 SAM2 mask…");
    try {
      const preview = await previewObjectMask({
        assetId,
        objectBbox,
        maskIndex: selectedMaskIndex ?? undefined,
      });
      setPreviewResult(preview);
      setSelectedMaskIndex(preview.selected_mask_index);
      setMessage("对象 mask 预览已更新。你可以切换候选或手工修边。");
    } catch {
      setMessage("对象 SAM2 mask 预览失败，请检查后端日志。");
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function runGeneration() {
    if (objectBbox === null) {
      return;
    }
    setMessage("正在把 SAM 3D Objects 任务加入后台队列…");
    try {
      const job = await triggerSam3dObject({
        assetId,
        objectBbox,
        maskIndex: selectedMaskIndex ?? undefined,
        previewId: previewResult?.preview_id ?? undefined,
        maskEdits: maskEdits.length > 0 ? maskEdits : undefined,
      });
      setJobId(job.id);
      setMessage(`任务 #${job.id} 已入队，后台处理中。`);
    } catch {
      setMessage("对象 3D 任务创建失败，请检查后端是否可用。");
    }
  }

  function resetBbox() {
    if (imageSize === null) {
      return;
    }
    setObjectBbox(defaultObjectBbox(imageSize));
    setPreviewResult(null);
    setSelectedMaskIndex(null);
    setMaskEdits([]);
  }

  const selectedPreviewCandidate =
    previewResult?.candidates.find((item) => item.index === selectedMaskIndex) ??
    previewResult?.candidates[0] ??
    null;
  const selectedPreviewOverlayUrl = getPreviewUrl(selectedPreviewCandidate?.overlay_url ?? null);
  const selectedPreviewMaskUrl = getPreviewUrl(selectedPreviewCandidate?.mask_url ?? null);

  return (
    <div className="body-reconstruction-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">SAM 3D Objects</p>
          <h2>物体 3D 工作区</h2>
        </div>
      </div>
      <p className="muted-copy">{message}</p>

      {sourcePreviewUrl && objectBbox ? (
        <div className="body-editor-shell">
          <div className="body-editor-column">
            <div className="body-editor-header">
              <div>
                <p className="eyebrow">Step 1</p>
                <h3>框住目标物体</h3>
              </div>
              <button type="button" className="pill-button" onClick={resetBbox}>
                重置框
              </button>
            </div>
            <BodyBboxEditor
              imageUrl={sourcePreviewUrl}
              face={null}
              bbox={objectBbox}
              onChange={setObjectBbox}
              onImageSizeChange={setImageSize}
            />
            <div className="body-bbox-readout">
              <span>{`x1 ${objectBbox[0].toFixed(0)}`}</span>
              <span>{`y1 ${objectBbox[1].toFixed(0)}`}</span>
              <span>{`x2 ${objectBbox[2].toFixed(0)}`}</span>
              <span>{`y2 ${objectBbox[3].toFixed(0)}`}</span>
            </div>
            <div className="body-run-actions">
              <button type="button" className="pill-button" onClick={() => void runPreview()} disabled={isPreviewLoading || jobId !== null}>
                {isPreviewLoading ? "预览中…" : "预览 mask"}
              </button>
              <button type="button" className="pill-button accent" onClick={() => void runGeneration()} disabled={jobId !== null}>
                {jobId !== null ? "处理中…" : "开始生成对象 3D"}
              </button>
            </div>
          </div>

          <div className="body-editor-column">
            <div className="body-editor-header">
              <div>
                <p className="eyebrow">Step 2</p>
                <h3>挑选并微调对象 mask</h3>
              </div>
            </div>
            <div className="body-preview-stage">
              {selectedPreviewOverlayUrl ? (
                <img src={selectedPreviewOverlayUrl} alt="Object SAM2 preview" />
              ) : (
                <img src={sourcePreviewUrl} alt="Object source preview" />
              )}
            </div>
            {previewResult ? (
              <div className="body-mask-workbench">
                <div className="body-mask-candidates">
                  {previewResult.candidates.map((candidate) => {
                    const overlayUrl = getPreviewUrl(candidate.overlay_url);
                    return (
                      <button
                        type="button"
                        key={candidate.index}
                        className={`body-mask-candidate ${selectedMaskIndex === candidate.index ? "active" : ""}`}
                        onClick={() => setSelectedMaskIndex(candidate.index)}
                      >
                        {overlayUrl ? <img src={overlayUrl} alt={`Object mask ${candidate.index}`} /> : null}
                        <strong>{`Mask ${candidate.index}`}</strong>
                        <span>{`score ${candidate.score.toFixed(3)}`}</span>
                      </button>
                    );
                  })}
                </div>
                {selectedPreviewMaskUrl ? (
                  <div className="body-mask-editor-shell">
                    <div className="body-mask-toolbar">
                      <div className="body-mask-mode-group">
                        <button
                          type="button"
                          className={`pill-button ${maskBrushMode === "add" ? "accent" : ""}`}
                          onClick={() => setMaskBrushMode("add")}
                        >
                          补面
                        </button>
                        <button
                          type="button"
                          className={`pill-button ${maskBrushMode === "erase" ? "accent" : ""}`}
                          onClick={() => setMaskBrushMode("erase")}
                        >
                          擦除
                        </button>
                      </div>
                      <label className="body-mask-radius-control">
                        <span>{`笔刷 ${maskBrushRadius}px`}</span>
                        <input
                          type="range"
                          min="8"
                          max="120"
                          step="2"
                          value={maskBrushRadius}
                          onChange={(event) => setMaskBrushRadius(Number(event.target.value))}
                        />
                      </label>
                      <button
                        type="button"
                        className="pill-button"
                        onClick={() => setMaskEdits([])}
                        disabled={maskEdits.length === 0}
                      >
                        重置 mask 编辑
                      </button>
                    </div>
                    <BodyMaskEditor
                      imageUrl={sourcePreviewUrl}
                      maskUrl={selectedPreviewMaskUrl}
                      edits={maskEdits}
                      mode={maskBrushMode}
                      brushRadius={maskBrushRadius}
                      onChange={setMaskEdits}
                    />
                    <p className="muted-copy">
                      {maskEdits.length > 0
                        ? `已记录 ${maskEdits.length} 笔物体 mask 修正，生成时会直接使用。`
                        : "如果边缘不准，可以用补面 / 擦除对刷一遍。"}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="empty-state compact">
                <h3>还没有对象 mask 预览</h3>
                <p>先拖拽物体框，再点“预览 mask”。</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="empty-state compact">
          <h3>当前没有可用预览图</h3>
          <p>这张照片还没有 hero JPG 预览，暂时无法运行 SAM 3D Objects。</p>
        </div>
      )}

      <div className="body-run-list">
        {reconstructions.length === 0 ? (
          <div className="empty-state compact">
            <h3>还没有对象运行记录</h3>
            <p>第一次点击后，这里会显示 mask 预览、GLB 预览和下载入口。</p>
          </div>
        ) : (
          reconstructions.map((run) => {
            const overlayUrl = getPreviewUrl(run.overlay_url);
            const glbUrl = getPreviewUrl(run.glb_url);
            const glbDownloadUrl = getPreviewUrl(run.glb_download_url);
            const plyUrl = getPreviewUrl(run.gaussian_ply_url);
            const bundleUrl = getPreviewUrl(run.bundle_url);
            return (
              <article key={run.id} className="body-run-card">
                <div className="body-run-card-header">
                  <div>
                    <p className="eyebrow">Object Run #{run.id}</p>
                    <h3>单物体重建</h3>
                  </div>
                  <span className={`body-run-status ${run.status}`}>{formatRunStatus(run.status)}</span>
                </div>
                <p className="muted-copy">
                  {new Date(run.created_at).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" })}
                </p>
                {glbUrl ? <ObjectGlbViewer glbUrl={glbUrl} /> : null}
                {!glbUrl ? (
                  <div className="body-run-media">
                    {overlayUrl ? <img src={overlayUrl} alt={`Object run ${run.id}`} /> : <div className="asset-thumb fallback">No Preview</div>}
                  </div>
                ) : null}
                <p className="muted-copy">
                  {run.status === "completed"
                    ? "对象 3D 输出已经生成，可直接网页预览或下载 GLB / PLY。"
                    : run.error_message ?? "任务正在处理中。"}
                </p>
                <div className="body-run-actions">
                  {bundleUrl ? (
                    <a href={bundleUrl} className="pill-link" download>
                      下载 bundle
                    </a>
                  ) : null}
                  {glbDownloadUrl ? (
                    <a href={glbDownloadUrl} className="pill-link" download>
                      下载 GLB
                    </a>
                  ) : null}
                  {plyUrl ? (
                    <a href={plyUrl} className="pill-link" download>
                      下载 PLY
                    </a>
                  ) : null}
                </div>
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}

function defaultObjectBbox(imageSize: { width: number; height: number }): number[] {
  const x1 = imageSize.width * 0.18;
  const y1 = imageSize.height * 0.16;
  const x2 = imageSize.width * 0.82;
  const y2 = imageSize.height * 0.84;
  return [round2(x1), round2(y1), round2(x2), round2(y2)];
}

function formatRunStatus(status: string): string {
  switch (status) {
    case "pending":
      return "排队中";
    case "running":
      return "处理中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
