"use client";

import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { Face } from "@/lib/types";

type ResizeHandle = "move" | "nw" | "ne" | "sw" | "se";

type BodyBboxEditorProps = {
  imageUrl: string;
  face?: Face | null;
  bbox: number[];
  onChange: (bbox: number[]) => void;
  onImageSizeChange?: (size: { width: number; height: number }) => void;
};

type DragState = {
  handle: ResizeHandle;
  startX: number;
  startY: number;
  startBbox: number[];
};

export function BodyBboxEditor({ imageUrl, face = null, bbox, onChange, onImageSizeChange }: BodyBboxEditorProps) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);

  const normalizedBbox = useMemo(() => {
    if (!imageSize) {
      return null;
    }
    const [x1, y1, x2, y2] = bbox;
    return {
      left: `${(x1 / imageSize.width) * 100}%`,
      top: `${(y1 / imageSize.height) * 100}%`,
      width: `${((x2 - x1) / imageSize.width) * 100}%`,
      height: `${((y2 - y1) / imageSize.height) * 100}%`,
    };
  }, [bbox, imageSize]);

  const normalizedFace = useMemo(() => {
    if (!imageSize || !face) {
      return null;
    }
    return {
      left: `${(face.bbox_x1 / imageSize.width) * 100}%`,
      top: `${(face.bbox_y1 / imageSize.height) * 100}%`,
      width: `${((face.bbox_x2 - face.bbox_x1) / imageSize.width) * 100}%`,
      height: `${((face.bbox_y2 - face.bbox_y1) / imageSize.height) * 100}%`,
    };
  }, [face, imageSize]);

  useEffect(() => {
    if (drag === null || imageSize === null) {
      return;
    }

    const onPointerMove = (event: PointerEvent | globalThis.PointerEvent) => {
      const frame = frameRef.current;
      if (!frame) {
        return;
      }
      const rect = frame.getBoundingClientRect();
      if (!rect.width || !rect.height) {
        return;
      }

      const deltaX = ((event.clientX - drag.startX) / rect.width) * imageSize.width;
      const deltaY = ((event.clientY - drag.startY) / rect.height) * imageSize.height;
      const [startX1, startY1, startX2, startY2] = drag.startBbox;
      let next = [startX1, startY1, startX2, startY2];

      if (drag.handle === "move") {
        const boxWidth = startX2 - startX1;
        const boxHeight = startY2 - startY1;
        let nextX1 = startX1 + deltaX;
        let nextY1 = startY1 + deltaY;
        nextX1 = clamp(nextX1, 0, imageSize.width - boxWidth);
        nextY1 = clamp(nextY1, 0, imageSize.height - boxHeight);
        next = [nextX1, nextY1, nextX1 + boxWidth, nextY1 + boxHeight];
      } else {
        const minSize = 40;
        let [x1, y1, x2, y2] = next;
        if (drag.handle.includes("n")) {
          y1 = clamp(startY1 + deltaY, 0, startY2 - minSize);
        }
        if (drag.handle.includes("s")) {
          y2 = clamp(startY2 + deltaY, startY1 + minSize, imageSize.height);
        }
        if (drag.handle.includes("w")) {
          x1 = clamp(startX1 + deltaX, 0, startX2 - minSize);
        }
        if (drag.handle.includes("e")) {
          x2 = clamp(startX2 + deltaX, startX1 + minSize, imageSize.width);
        }
        next = [x1, y1, x2, y2];
      }

      onChange(next.map((value) => round2(value)));
    };

    const onPointerUp = () => {
      setDrag(null);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [drag, imageSize, onChange]);

  function startDrag(handle: ResizeHandle, event: PointerEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
    setDrag({
      handle,
      startX: event.clientX,
      startY: event.clientY,
      startBbox: [...bbox],
    });
  }

  return (
    <div className="body-bbox-editor">
      <div ref={frameRef} className="body-bbox-stage">
        <img
          src={imageUrl}
          alt="Body selection preview"
          onLoad={(event) => {
            const size = {
              width: event.currentTarget.naturalWidth,
              height: event.currentTarget.naturalHeight,
            };
            setImageSize(size);
            onImageSizeChange?.(size);
          }}
        />
        {normalizedFace ? <div className="body-bbox-face" style={normalizedFace} /> : null}
        {normalizedBbox ? (
          <div
            className="body-bbox-rect"
            style={normalizedBbox}
            onPointerDown={(event) => startDrag("move", event)}
          >
            <button type="button" className="body-bbox-handle nw" onPointerDown={(event) => startDrag("nw", event)} />
            <button type="button" className="body-bbox-handle ne" onPointerDown={(event) => startDrag("ne", event)} />
            <button type="button" className="body-bbox-handle sw" onPointerDown={(event) => startDrag("sw", event)} />
            <button type="button" className="body-bbox-handle se" onPointerDown={(event) => startDrag("se", event)} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
