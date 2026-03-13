"use client";

import { PointerEvent, useEffect, useRef, useState } from "react";

import { BodyMaskEditStroke } from "@/lib/types";

type BodyMaskEditorProps = {
  imageUrl: string;
  maskUrl: string;
  edits: BodyMaskEditStroke[];
  mode: "add" | "erase";
  brushRadius: number;
  onChange: (edits: BodyMaskEditStroke[]) => void;
  onImageSizeChange?: (size: { width: number; height: number }) => void;
};

export function BodyMaskEditor({
  imageUrl,
  maskUrl,
  edits,
  mode,
  brushRadius,
  onChange,
  onImageSizeChange,
}: BodyMaskEditorProps) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sourceImageRef = useRef<HTMLImageElement | null>(null);
  const baseMaskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const workingMaskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const draftStrokeRef = useRef<BodyMaskEditStroke | null>(null);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReady(false);

    const sourceImage = new window.Image();
    sourceImage.crossOrigin = "anonymous";
    const maskImage = new window.Image();
    maskImage.crossOrigin = "anonymous";

    const loadImage = (image: HTMLImageElement, src: string) =>
      new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error(`Failed to load ${src}`));
        image.src = src;
      });

    void Promise.all([loadImage(sourceImage, imageUrl), loadImage(maskImage, maskUrl)])
      .then(() => {
        if (cancelled) {
          return;
        }
        const width = sourceImage.naturalWidth;
        const height = sourceImage.naturalHeight;
        sourceImageRef.current = sourceImage;

        const baseMaskCanvas = document.createElement("canvas");
        baseMaskCanvas.width = width;
        baseMaskCanvas.height = height;
        const baseMaskContext = baseMaskCanvas.getContext("2d");
        baseMaskContext?.drawImage(maskImage, 0, 0, width, height);
        baseMaskCanvasRef.current = baseMaskCanvas;

        workingMaskCanvasRef.current = document.createElement("canvas");
        workingMaskCanvasRef.current.width = width;
        workingMaskCanvasRef.current.height = height;

        overlayCanvasRef.current = document.createElement("canvas");
        overlayCanvasRef.current.width = width;
        overlayCanvasRef.current.height = height;

        const nextSize = { width, height };
        setImageSize(nextSize);
        onImageSizeChange?.(nextSize);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) {
          setReady(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [imageUrl, maskUrl, onImageSizeChange]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    drawComposite(edits);
  }, [edits, imageSize, ready]);

  function drawStroke(
    context: CanvasRenderingContext2D,
    stroke: BodyMaskEditStroke,
    width: number,
    height: number,
  ) {
    const points = stroke.points.map((point) => ({
      x: clamp(point.x, 0, width),
      y: clamp(point.y, 0, height),
    }));
    if (points.length === 0) {
      return;
    }
    const radius = Math.max(1, stroke.radius);
    const fillStyle = stroke.mode === "add" ? "#ffffff" : "#000000";
    context.save();
    context.strokeStyle = fillStyle;
    context.fillStyle = fillStyle;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.lineWidth = radius * 2;
    if (points.length === 1) {
      context.beginPath();
      context.arc(points[0].x, points[0].y, radius, 0, Math.PI * 2);
      context.fill();
      context.restore();
      return;
    }
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach((point) => {
      context.lineTo(point.x, point.y);
    });
    context.stroke();
    points.forEach((point) => {
      context.beginPath();
      context.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context.fill();
    });
    context.restore();
  }

  function drawComposite(strokes: BodyMaskEditStroke[], draftStroke?: BodyMaskEditStroke | null) {
    const canvas = canvasRef.current;
    const sourceImage = sourceImageRef.current;
    const baseMaskCanvas = baseMaskCanvasRef.current;
    const workingMaskCanvas = workingMaskCanvasRef.current;
    const overlayCanvas = overlayCanvasRef.current;
    if (!canvas || !sourceImage || !baseMaskCanvas || !workingMaskCanvas || !overlayCanvas || !imageSize) {
      return;
    }

    const { width, height } = imageSize;
    canvas.width = width;
    canvas.height = height;
    workingMaskCanvas.width = width;
    workingMaskCanvas.height = height;
    overlayCanvas.width = width;
    overlayCanvas.height = height;

    const workingMaskContext = workingMaskCanvas.getContext("2d");
    const overlayContext = overlayCanvas.getContext("2d");
    const context = canvas.getContext("2d");
    if (!workingMaskContext || !overlayContext || !context) {
      return;
    }

    workingMaskContext.clearRect(0, 0, width, height);
    workingMaskContext.drawImage(baseMaskCanvas, 0, 0, width, height);
    strokes.forEach((stroke) => drawStroke(workingMaskContext, stroke, width, height));
    if (draftStroke) {
      drawStroke(workingMaskContext, draftStroke, width, height);
    }

    overlayContext.clearRect(0, 0, width, height);
    overlayContext.drawImage(workingMaskCanvas, 0, 0, width, height);
    overlayContext.globalCompositeOperation = "source-in";
    overlayContext.fillStyle = "rgba(255, 139, 56, 0.58)";
    overlayContext.fillRect(0, 0, width, height);
    overlayContext.globalCompositeOperation = "source-over";

    context.clearRect(0, 0, width, height);
    context.drawImage(sourceImage, 0, 0, width, height);
    context.drawImage(overlayCanvas, 0, 0, width, height);
  }

  function pointFromEvent(event: PointerEvent<HTMLDivElement>) {
    if (!imageSize) {
      return null;
    }
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) {
      return null;
    }
    return {
      x: clamp(((event.clientX - rect.left) / rect.width) * imageSize.width, 0, imageSize.width),
      y: clamp(((event.clientY - rect.top) / rect.height) * imageSize.height, 0, imageSize.height),
    };
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    const point = pointFromEvent(event);
    if (!point) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const nextStroke: BodyMaskEditStroke = {
      mode,
      radius: brushRadius,
      points: [point],
    };
    draftStrokeRef.current = nextStroke;
    drawComposite(edits, nextStroke);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const point = pointFromEvent(event);
    const currentStroke = draftStrokeRef.current;
    if (!point || !currentStroke) {
      return;
    }
    event.preventDefault();
    currentStroke.points.push(point);
    draftStrokeRef.current = currentStroke;
    drawComposite(edits, currentStroke);
  }

  function finalizeStroke() {
    const currentStroke = draftStrokeRef.current;
    draftStrokeRef.current = null;
    if (!currentStroke || currentStroke.points.length === 0) {
      drawComposite(edits);
      return;
    }
    onChange([...edits, currentStroke]);
  }

  return (
    <div className="body-mask-editor">
      <div
        ref={stageRef}
        className="body-mask-stage"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finalizeStroke}
        onPointerCancel={finalizeStroke}
      >
        <canvas ref={canvasRef} />
        {!ready ? <div className="body-mask-loading">正在加载 mask 编辑器…</div> : null}
      </div>
    </div>
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
