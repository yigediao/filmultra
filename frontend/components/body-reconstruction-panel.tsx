"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { BodyBboxEditor } from "@/components/body-bbox-editor";
import { BodyMeshViewer } from "@/components/body-mesh-viewer";
import { BodyMaskEditor } from "@/components/body-mask-editor";
import { getJob, getPreviewUrl, previewBodyMask, triggerSam3dBody } from "@/lib/api";
import { BodyMaskEditStroke, BodyReconstruction, BodyReconstructionPreview, Face } from "@/lib/types";

type BodyReconstructionPanelProps = {
  assetId: number;
  heroPreviewUrl: string | null;
  faces: Face[];
  reconstructions: BodyReconstruction[];
};

export function BodyReconstructionPanel({
  assetId,
  heroPreviewUrl,
  faces,
  reconstructions,
}: BodyReconstructionPanelProps) {
  const router = useRouter();
  const [jobId, setJobId] = useState<number | null>(null);
  const [message, setMessage] = useState("先选一张脸，再手工微调人体框并预览 mask。");
  const [isPending, startTransition] = useTransition();
  const [selectedFaceId, setSelectedFaceId] = useState<number | null>(faces[0]?.id ?? null);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [bodyBbox, setBodyBbox] = useState<number[] | null>(null);
  const [previewResult, setPreviewResult] = useState<BodyReconstructionPreview | null>(null);
  const [selectedMaskIndex, setSelectedMaskIndex] = useState<number | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [maskEdits, setMaskEdits] = useState<BodyMaskEditStroke[]>([]);
  const [maskBrushMode, setMaskBrushMode] = useState<"add" | "erase">("add");
  const [maskBrushRadius, setMaskBrushRadius] = useState(28);

  const selectedFace = useMemo(
    () => faces.find((face) => face.id === selectedFaceId) ?? null,
    [faces, selectedFaceId],
  );

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
            setMessage(`任务 #${job.id} 正在后台执行 SAM2 / SAM 3D Body。`);
          } else if (job.status === "completed") {
            setMessage("3D 重建任务已完成。");
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
          setMessage("无法获取 3D 任务状态，请检查后端是否仍在运行。");
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
    setPreviewResult(null);
    setSelectedMaskIndex(null);
    setMaskEdits([]);
    if (selectedFace === null) {
      setBodyBbox(null);
      return;
    }
    setBodyBbox(deriveLooseBodyBbox(selectedFace));
  }, [selectedFace]);

  useEffect(() => {
    setMaskEdits([]);
  }, [previewResult?.preview_id, selectedMaskIndex]);

  useEffect(() => {
    if (selectedFace === null || imageSize === null) {
      return;
    }
    setBodyBbox((current) => {
      if (current === null) {
        return deriveBodyBbox(selectedFace, imageSize);
      }
      return [
        round2(clamp(current[0], 0, imageSize.width - 1)),
        round2(clamp(current[1], 0, imageSize.height - 1)),
        round2(clamp(current[2], Math.min(current[0] + 40, imageSize.width), imageSize.width)),
        round2(clamp(current[3], Math.min(current[1] + 40, imageSize.height), imageSize.height)),
      ];
    });
  }, [selectedFace, imageSize]);

  async function runPreview() {
    if (selectedFace === null || bodyBbox === null) {
      return;
    }

    setIsPreviewLoading(true);
    setMessage("正在预览 SAM2 mask…");
    try {
      const preview = await previewBodyMask({
        assetId,
        faceId: selectedFace.id,
        bodyBbox,
        maskIndex: selectedMaskIndex ?? undefined,
      });
      setPreviewResult(preview);
      setSelectedMaskIndex(preview.selected_mask_index);
      setMessage("SAM2 mask 预览已更新。你可以切换候选 mask，再开始生成 3D。");
    } catch {
      setMessage("SAM2 mask 预览失败，请检查后端日志。");
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function runGeneration() {
    if (selectedFace === null || bodyBbox === null) {
      return;
    }
    setMessage("正在把 SAM 3D Body 任务加入后台队列…");
    try {
      const job = await triggerSam3dBody({
        assetId,
        faceId: selectedFace.id,
        bodyBbox,
        maskIndex: selectedMaskIndex ?? undefined,
        previewId: previewResult?.preview_id ?? undefined,
        maskEdits: maskEdits.length > 0 ? maskEdits : undefined,
      });
      setJobId(job.id);
      setMessage(`任务 #${job.id} 已入队，后台处理中。`);
    } catch {
      setMessage("任务创建失败，请检查后端是否可用。");
    }
  }

  function resetBbox() {
    if (selectedFace === null || imageSize === null) {
      return;
    }
    setBodyBbox(deriveBodyBbox(selectedFace, imageSize));
    setPreviewResult(null);
    setSelectedMaskIndex(null);
  }

  const selectedPreviewCandidate = previewResult?.candidates.find((item) => item.index === selectedMaskIndex) ?? previewResult?.candidates[0] ?? null;
  const selectedPreviewOverlayUrl = getPreviewUrl(selectedPreviewCandidate?.overlay_url ?? null);
  const selectedPreviewMaskUrl = getPreviewUrl(selectedPreviewCandidate?.mask_url ?? null);
  const sourcePreviewUrl = previewResult ? getPreviewUrl(previewResult.source_image_url) : heroPreviewUrl ? getPreviewUrl(heroPreviewUrl) : null;

  return (
    <div className="body-reconstruction-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">SAM 3D Body</p>
          <h2>人体 3D 工作区</h2>
        </div>
      </div>
      <p className="muted-copy">{message}</p>

      {faces.length === 0 ? (
        <div className="empty-state compact">
          <h3>当前没有可用人脸</h3>
          <p>先对这张照片跑人物检测，再选择一张脸触发人体 3D 流程。</p>
        </div>
      ) : (
        <div className="body-face-grid">
          {faces.map((face) => {
            const previewUrl = getPreviewUrl(face.preview_url);
            const label = face.person_name ?? face.cluster_id ?? `Face #${face.face_index + 1}`;
            const isActive = selectedFaceId === face.id;

            return (
              <button
                type="button"
                key={face.id}
                className={`body-face-card ${isActive ? "active" : ""}`}
                onClick={() => setSelectedFaceId(face.id)}
              >
                <div className="body-face-card-media">
                  {previewUrl ? (
                    <img src={previewUrl} alt={label} />
                  ) : (
                    <div className="asset-thumb fallback">No Face</div>
                  )}
                </div>
                <div className="body-face-card-meta">
                  <strong>{label}</strong>
                  <span>{Math.round(face.confidence * 100)}% face confidence</span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {selectedFace !== null && sourcePreviewUrl && bodyBbox !== null ? (
        <div className="body-editor-shell">
          <div className="body-editor-column">
            <div className="body-editor-header">
              <div>
                <p className="eyebrow">Step 1</p>
                <h3>微调人体框</h3>
              </div>
              <button type="button" className="pill-button" onClick={resetBbox}>
                重置框
              </button>
            </div>
            <BodyBboxEditor
              imageUrl={sourcePreviewUrl}
              face={selectedFace}
              bbox={bodyBbox}
              onChange={setBodyBbox}
              onImageSizeChange={setImageSize}
            />
            <div className="body-bbox-readout">
              <span>{`x1 ${bodyBbox[0].toFixed(0)}`}</span>
              <span>{`y1 ${bodyBbox[1].toFixed(0)}`}</span>
              <span>{`x2 ${bodyBbox[2].toFixed(0)}`}</span>
              <span>{`y2 ${bodyBbox[3].toFixed(0)}`}</span>
            </div>
            <div className="body-run-actions">
              <button type="button" className="pill-button" onClick={() => void runPreview()} disabled={isPreviewLoading || jobId !== null}>
                {isPreviewLoading ? "预览中…" : "预览 mask"}
              </button>
              <button type="button" className="pill-button accent" onClick={() => void runGeneration()} disabled={jobId !== null}>
                {jobId !== null ? "处理中…" : "开始生成 3D"}
              </button>
            </div>
          </div>

          <div className="body-editor-column">
            <div className="body-editor-header">
              <div>
                <p className="eyebrow">Step 2</p>
                <h3>挑选并微调 SAM2 mask</h3>
              </div>
            </div>
            <div className="body-preview-stage">
              {selectedPreviewOverlayUrl ? (
                <img src={selectedPreviewOverlayUrl} alt="SAM2 preview" />
              ) : sourcePreviewUrl ? (
                <img src={sourcePreviewUrl} alt="Source preview" />
              ) : (
                <div className="asset-thumb fallback">No Preview</div>
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
                        {overlayUrl ? <img src={overlayUrl} alt={`Mask ${candidate.index}`} /> : null}
                        <strong>{`Mask ${candidate.index}`}</strong>
                        <span>{`score ${candidate.score.toFixed(3)}`}</span>
                      </button>
                    );
                  })}
                </div>
                {selectedPreviewMaskUrl && sourcePreviewUrl ? (
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
                        ? `已记录 ${maskEdits.length} 笔手工修正，生成 3D 时会直接使用修正后的 mask。`
                        : "先挑一个候选 mask；如果边缘不准，可以用补面 / 擦除对刷一遍。"}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="empty-state compact">
                <h3>还没有 mask 预览</h3>
                <p>先拖拽人体框，再点“预览 mask”。</p>
              </div>
            )}
          </div>
        </div>
      ) : null}

      <div className="body-run-list">
        {reconstructions.length === 0 ? (
          <div className="empty-state compact">
            <h3>还没有运行记录</h3>
            <p>第一次点击后，这里会显示分割预览、3D 预览和下载入口。</p>
          </div>
        ) : (
          reconstructions.map((run) => {
            const overlayUrl = getPreviewUrl(run.overlay_url);
            const facePreviewUrl = getPreviewUrl(run.face_preview_url);
            const bundleUrl = getPreviewUrl(run.bundle_url);
            const meshUrl = getPreviewUrl(run.mesh_object_urls[0] ?? null);
            return (
              <article key={run.id} className="body-run-card">
                <div className="body-run-card-header">
                  <div>
                    <p className="eyebrow">Run #{run.id}</p>
                    <h3>{run.person_name ?? "未命名人物"}</h3>
                  </div>
                  <span className={`body-run-status ${run.status}`}>{formatRunStatus(run.status)}</span>
                </div>
                <p className="muted-copy">
                  {new Date(run.created_at).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" })}
                </p>
                {meshUrl ? <BodyMeshViewer meshUrl={meshUrl} /> : null}
                {!meshUrl ? (
                  <div className="body-run-media">
                    {overlayUrl ? (
                      <img src={overlayUrl} alt={`Body run ${run.id}`} />
                    ) : facePreviewUrl ? (
                      <img src={facePreviewUrl} alt={`Face ${run.face_id ?? run.id}`} />
                    ) : (
                      <div className="asset-thumb fallback">No Preview</div>
                    )}
                  </div>
                ) : null}
                <p className="muted-copy">
                  {run.status === "awaiting_weights"
                    ? "SAM2 已完成，当前缺少 SAM 3D Body 官方权重。"
                    : run.status === "completed"
                      ? "3D 输出已经生成，可直接网页预览或下载 OBJ。"
                      : run.error_message ?? "任务正在处理中。"}
                </p>
                <div className="body-run-actions">
                  {bundleUrl ? (
                    <a href={bundleUrl} className="pill-link" download>
                      下载 bundle
                    </a>
                  ) : null}
                  {run.mesh_object_urls.map((url, index) => {
                    const downloadUrl = getPreviewUrl(url);
                    return (
                      <a key={url} href={downloadUrl ?? url} className="pill-link" download>
                        {`下载 OBJ ${index + 1}`}
                      </a>
                    );
                  })}
                </div>
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}

function deriveBodyBbox(face: Face, imageSize: { width: number; height: number }): number[] {
  const faceWidth = face.bbox_x2 - face.bbox_x1;
  const faceHeight = face.bbox_y2 - face.bbox_y1;
  const faceCenterX = (face.bbox_x1 + face.bbox_x2) / 2;

  const x1 = clamp(faceCenterX - faceWidth * 3, 0, imageSize.width - 1);
  const y1 = clamp(face.bbox_y1 - faceHeight * 1.4, 0, imageSize.height - 1);
  const x2 = clamp(faceCenterX + faceWidth * 3, x1 + 40, imageSize.width);
  const y2 = clamp(face.bbox_y2 + faceHeight * 8.6, y1 + 40, imageSize.height);
  return [round2(x1), round2(y1), round2(x2), round2(y2)];
}

function deriveLooseBodyBbox(face: Face): number[] {
  const faceWidth = face.bbox_x2 - face.bbox_x1;
  const faceHeight = face.bbox_y2 - face.bbox_y1;
  const faceCenterX = (face.bbox_x1 + face.bbox_x2) / 2;
  return [
    round2(faceCenterX - faceWidth * 3),
    round2(face.bbox_y1 - faceHeight * 1.4),
    round2(faceCenterX + faceWidth * 3),
    round2(face.bbox_y2 + faceHeight * 8.6),
  ];
}

function formatRunStatus(status: string): string {
  switch (status) {
    case "pending":
      return "排队中";
    case "running":
      return "处理中";
    case "awaiting_weights":
      return "缺权重";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
