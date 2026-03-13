"use client";

import { useEffect, useRef, useState } from "react";

type AssetViewerProps = {
  previewUrl: string | null;
  displayUrl: string | null;
  alt: string;
  width?: number | null;
  height?: number | null;
};

const MIN_SCALE = 1;
const MAX_SCALE = 4;
const SCALE_STEP = 0.25;
const MINIMAP_MAX_SIZE = 152;
const MINIMAP_MIN_SIZE = 88;

type Dimensions = {
  width: number;
  height: number;
};

type Point = {
  x: number;
  y: number;
};

type ZoomMetrics = {
  renderedWidth: number;
  renderedHeight: number;
  overflowX: number;
  overflowY: number;
  marginLeft: number;
  marginTop: number;
};

type MinimapViewport = {
  width: number;
  height: number;
  left: number;
  top: number;
  visibleWidthRatio: number;
  visibleHeightRatio: number;
  leftRatio: number;
  topRatio: number;
};

function clampScale(value: number) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Number(value.toFixed(2))));
}

function clampValue(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function getZoomMetrics(imageDimensions: Dimensions | null, viewportSize: Dimensions, scale: number): ZoomMetrics | null {
  if (!imageDimensions || viewportSize.width <= 0 || viewportSize.height <= 0) {
    return null;
  }

  const fitScale = Math.min(
    viewportSize.width / imageDimensions.width,
    viewportSize.height / imageDimensions.height,
  );
  const renderedWidth = imageDimensions.width * fitScale * scale;
  const renderedHeight = imageDimensions.height * fitScale * scale;
  const overflowX = Math.max(0, renderedWidth - viewportSize.width);
  const overflowY = Math.max(0, renderedHeight - viewportSize.height);

  return {
    renderedWidth,
    renderedHeight,
    overflowX,
    overflowY,
    marginLeft: overflowX > 0 ? 0 : (viewportSize.width - renderedWidth) / 2,
    marginTop: overflowY > 0 ? 0 : (viewportSize.height - renderedHeight) / 2,
  };
}

function getMinimapSize(imageDimensions: Dimensions | null) {
  if (!imageDimensions || imageDimensions.width <= 0 || imageDimensions.height <= 0) {
    return null;
  }

  const aspect = imageDimensions.width / imageDimensions.height;

  if (aspect >= 1) {
    return {
      width: MINIMAP_MAX_SIZE,
      height: Math.max(MINIMAP_MIN_SIZE, Math.round(MINIMAP_MAX_SIZE / aspect)),
    };
  }

  return {
    width: Math.max(MINIMAP_MIN_SIZE, Math.round(MINIMAP_MAX_SIZE * aspect)),
    height: MINIMAP_MAX_SIZE,
  };
}

function getMinimapContentSize(element: HTMLDivElement | null, fallback: Dimensions | null): Dimensions | null {
  if (element) {
    return {
      width: element.clientWidth,
      height: element.clientHeight,
    };
  }

  return fallback;
}

async function resolveDisplayedImageDimensions(image: HTMLImageElement): Promise<Dimensions> {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(image);
      const dimensions = {
        width: bitmap.width,
        height: bitmap.height,
      };
      bitmap.close();

      if (dimensions.width > 0 && dimensions.height > 0) {
        return dimensions;
      }
    } catch {
      // Fall back to the image element intrinsic size.
    }
  }

  return {
    width: image.naturalWidth,
    height: image.naturalHeight,
  };
}

export function AssetViewer({ previewUrl, displayUrl, alt, width, height }: AssetViewerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const [isMinimapDragging, setIsMinimapDragging] = useState(false);
  const [viewOffset, setViewOffset] = useState<Point>({ x: 0, y: 0 });
  const [viewportSize, setViewportSize] = useState<Dimensions>({ width: 0, height: 0 });
  const [imageDimensions, setImageDimensions] = useState<Dimensions | null>(
    width && height ? { width, height } : null,
  );
  const stageRef = useRef<HTMLDivElement | null>(null);
  const minimapRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startOffsetX: number;
    startOffsetY: number;
  } | null>(null);
  const minimapDragStateRef = useRef<number | null>(null);
  const minimapViewportOffsetRef = useRef<Point | null>(null);
  const zoomMetrics = getZoomMetrics(imageDimensions, viewportSize, scale);
  const minimapSize = getMinimapSize(imageDimensions);
  const minimapContentSize = getMinimapContentSize(minimapRef.current, minimapSize);
  const orientationClass = imageDimensions
    ? imageDimensions.height > imageDimensions.width
      ? "portrait"
      : imageDimensions.width > imageDimensions.height
        ? "landscape"
        : "square"
    : width && height
      ? height > width
        ? "portrait"
        : width > height
          ? "landscape"
          : "square"
      : "unknown";

  useEffect(() => {
    document.body.dataset.assetZoomOpen = isOpen ? "true" : "false";
    document.body.style.overflow = isOpen ? "hidden" : "";

    return () => {
      delete document.body.dataset.assetZoomOpen;
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    if (width && height) {
      setImageDimensions({ width, height });
    }
  }, [height, width]);

  useEffect(() => {
    if (!isOpen || !stageRef.current) {
      return;
    }

    const stage = stageRef.current;
    const updateViewportSize = () => {
      setViewportSize({
        width: stage.clientWidth,
        height: stage.clientHeight,
      });
    };

    updateViewportSize();

    const observer = new ResizeObserver(updateViewportSize);
    observer.observe(stage);

    return () => {
      observer.disconnect();
    };
  }, [isOpen]);

  useEffect(() => {
    if (!zoomMetrics) {
      setViewOffset({ x: 0, y: 0 });
      return;
    }

    setViewOffset((current) => ({
      x: clampValue(current.x, 0, zoomMetrics.overflowX),
      y: clampValue(current.y, 0, zoomMetrics.overflowY),
    }));
  }, [zoomMetrics?.overflowX, zoomMetrics?.overflowY]);

  function resetZoom() {
    setScale(1);
    setViewOffset({ x: 0, y: 0 });
  }

  function syncImageDimensions(nextDimensions: Dimensions) {
    if (nextDimensions.width <= 0 || nextDimensions.height <= 0) {
      return;
    }

    setImageDimensions((current) => {
      if (current && current.width === nextDimensions.width && current.height === nextDimensions.height) {
        return current;
      }

      return nextDimensions;
    });
  }

  function updateZoom(nextScaleValue: number, focusPoint?: Point) {
    const nextScale = clampScale(nextScaleValue);

    if (nextScale === 1) {
      resetZoom();
      return;
    }

    if (!stageRef.current || !imageDimensions) {
      setScale(nextScale);
      return;
    }

    const stage = stageRef.current;
    const nextViewportSize = {
      width: stage.clientWidth,
      height: stage.clientHeight,
    };
    const currentMetrics = getZoomMetrics(imageDimensions, nextViewportSize, scale);
    const nextMetrics = getZoomMetrics(imageDimensions, nextViewportSize, nextScale);

    if (!currentMetrics || !nextMetrics) {
      setScale(nextScale);
      return;
    }

    const stageRect = stage.getBoundingClientRect();
    const localFocusX = focusPoint ? focusPoint.x - stageRect.left : nextViewportSize.width / 2;
    const localFocusY = focusPoint ? focusPoint.y - stageRect.top : nextViewportSize.height / 2;
    const currentImageLeft = currentMetrics.marginLeft - viewOffset.x;
    const currentImageTop = currentMetrics.marginTop - viewOffset.y;
    const focusRatioX = clampValue(
      (localFocusX - currentImageLeft) / currentMetrics.renderedWidth,
      0,
      1,
    );
    const focusRatioY = clampValue(
      (localFocusY - currentImageTop) / currentMetrics.renderedHeight,
      0,
      1,
    );

    setScale(nextScale);
    setViewOffset({
      x: clampValue(
        focusRatioX * nextMetrics.renderedWidth - localFocusX + nextMetrics.marginLeft,
        0,
        nextMetrics.overflowX,
      ),
      y: clampValue(
        focusRatioY * nextMetrics.renderedHeight - localFocusY + nextMetrics.marginTop,
        0,
        nextMetrics.overflowY,
      ),
    });
  }

  const minimapViewport: MinimapViewport | null =
    zoomMetrics && minimapContentSize
      ? (() => {
          const visibleWidthRatio = Math.min(1, viewportSize.width / zoomMetrics.renderedWidth);
          const visibleHeightRatio = Math.min(1, viewportSize.height / zoomMetrics.renderedHeight);
          const leftRatio = zoomMetrics.renderedWidth > 0 ? viewOffset.x / zoomMetrics.renderedWidth : 0;
          const topRatio = zoomMetrics.renderedHeight > 0 ? viewOffset.y / zoomMetrics.renderedHeight : 0;

          return {
            width: Math.max(20, minimapContentSize.width * visibleWidthRatio),
            height: Math.max(20, minimapContentSize.height * visibleHeightRatio),
            left: leftRatio * minimapContentSize.width,
            top: topRatio * minimapContentSize.height,
            visibleWidthRatio,
            visibleHeightRatio,
            leftRatio,
            topRatio,
          };
        })()
      : null;

  function updateOffsetFromMinimap(clientX: number, clientY: number, dragOffset?: Point) {
    if (!minimapRef.current || !zoomMetrics || !minimapViewport) {
      return;
    }

    const rect = minimapRef.current.getBoundingClientRect();
    const contentLeft = rect.left + minimapRef.current.clientLeft;
    const contentTop = rect.top + minimapRef.current.clientTop;
    const contentWidth = minimapRef.current.clientWidth;
    const contentHeight = minimapRef.current.clientHeight;
    const pointerRatioX = contentWidth > 0 ? clampValue((clientX - contentLeft) / contentWidth, 0, 1) : 0.5;
    const pointerRatioY = contentHeight > 0 ? clampValue((clientY - contentTop) / contentHeight, 0, 1) : 0.5;
    const leftRatio = clampValue(
      dragOffset ? pointerRatioX - dragOffset.x : pointerRatioX - minimapViewport.visibleWidthRatio / 2,
      0,
      1 - minimapViewport.visibleWidthRatio,
    );
    const topRatio = clampValue(
      dragOffset ? pointerRatioY - dragOffset.y : pointerRatioY - minimapViewport.visibleHeightRatio / 2,
      0,
      1 - minimapViewport.visibleHeightRatio,
    );

    setViewOffset({
      x: leftRatio * zoomMetrics.renderedWidth,
      y: topRatio * zoomMetrics.renderedHeight,
    });
  }

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setIsOpen(false);
      }
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        updateZoom(scale + SCALE_STEP);
      }
      if (event.key === "-") {
        event.preventDefault();
        updateZoom(scale - SCALE_STEP);
      }
      if (event.key === "0") {
        event.preventDefault();
        resetZoom();
      }
    }

    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen, scale, viewOffset, imageDimensions]);

  if (!previewUrl) {
    return <div className="asset-thumb fallback large">No Preview</div>;
  }

  function closeViewer() {
    setIsOpen(false);
    resetZoom();
    setIsDragging(false);
    setIsMinimapDragging(false);
    dragStateRef.current = null;
    minimapDragStateRef.current = null;
    minimapViewportOffsetRef.current = null;
  }

  function onStagePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (scale <= 1 || !zoomMetrics) {
      return;
    }

    event.preventDefault();
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startOffsetX: viewOffset.x,
      startOffsetY: viewOffset.y,
    };
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onStagePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStateRef.current || dragStateRef.current.pointerId !== event.pointerId || !zoomMetrics) {
      return;
    }

    event.preventDefault();
    const dragState = dragStateRef.current;
    setViewOffset({
      x: clampValue(dragState.startOffsetX - (event.clientX - dragState.startX), 0, zoomMetrics.overflowX),
      y: clampValue(dragState.startOffsetY - (event.clientY - dragState.startY), 0, zoomMetrics.overflowY),
    });
  }

  function finishStageDrag(event?: React.PointerEvent<HTMLDivElement>) {
    if (event && dragStateRef.current?.pointerId === event.pointerId) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    dragStateRef.current = null;
    setIsDragging(false);
  }

  function onMinimapPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!minimapViewport) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    minimapDragStateRef.current = event.pointerId;
    setIsMinimapDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);

    const rect = event.currentTarget.getBoundingClientRect();
    const contentLeft = rect.left + event.currentTarget.clientLeft;
    const contentTop = rect.top + event.currentTarget.clientTop;
    const contentWidth = event.currentTarget.clientWidth;
    const contentHeight = event.currentTarget.clientHeight;
    const pointerRatioX = contentWidth > 0 ? clampValue((event.clientX - contentLeft) / contentWidth, 0, 1) : 0.5;
    const pointerRatioY = contentHeight > 0 ? clampValue((event.clientY - contentTop) / contentHeight, 0, 1) : 0.5;
    const target = event.target;
    const isViewportHandle = target instanceof HTMLElement && target.dataset.minimapViewport === "true";

    if (isViewportHandle) {
      minimapViewportOffsetRef.current = {
        x: pointerRatioX - minimapViewport.leftRatio,
        y: pointerRatioY - minimapViewport.topRatio,
      };
      updateOffsetFromMinimap(event.clientX, event.clientY, minimapViewportOffsetRef.current);
      return;
    }

    minimapViewportOffsetRef.current = null;
    updateOffsetFromMinimap(event.clientX, event.clientY);
  }

  function onMinimapPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (minimapDragStateRef.current !== event.pointerId) {
      return;
    }

    event.preventDefault();
    updateOffsetFromMinimap(event.clientX, event.clientY, minimapViewportOffsetRef.current ?? undefined);
  }

  function finishMinimapDrag(event?: React.PointerEvent<HTMLDivElement>) {
    if (event && minimapDragStateRef.current === event.pointerId) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    minimapDragStateRef.current = null;
    minimapViewportOffsetRef.current = null;
    setIsMinimapDragging(false);
  }

  const imageLeft = zoomMetrics ? zoomMetrics.marginLeft - viewOffset.x : 0;
  const imageTop = zoomMetrics ? zoomMetrics.marginTop - viewOffset.y : 0;

  return (
    <>
      <button
        type="button"
        className={`asset-viewer-trigger ${orientationClass}`}
        onClick={() => {
          resetZoom();
          setIsOpen(true);
        }}
      >
        <img
          src={previewUrl}
          alt={alt}
          onLoad={(event) => {
            const image = event.currentTarget;
            void resolveDisplayedImageDimensions(image).then((dimensions) => {
              syncImageDimensions(dimensions);
            });
          }}
        />
        <span className="asset-viewer-hint">点击放大</span>
      </button>

      {isOpen ? (
        <div className="asset-zoom-overlay" role="dialog" aria-modal="true" onClick={() => closeViewer()}>
          <div className="asset-zoom-toolbar" onClick={(event) => event.stopPropagation()}>
            <p className="asset-zoom-copy">滚轮缩放 · 双击定点放大 · 拖动查看局部</p>
            <div className="asset-zoom-actions">
              <button type="button" className="pill-button" onClick={() => updateZoom(scale - SCALE_STEP)}>
                -
              </button>
              <span>{Math.round(scale * 100)}%</span>
              <button type="button" className="pill-button" onClick={() => updateZoom(scale + SCALE_STEP)}>
                +
              </button>
              <button type="button" className="pill-button" onClick={() => resetZoom()}>
                适应
              </button>
              <button type="button" className="pill-button accent" onClick={() => closeViewer()}>
                关闭
              </button>
            </div>
          </div>
          <div
            ref={stageRef}
            className={`asset-zoom-stage ${scale > 1 ? "zoomed" : ""} ${isDragging ? "dragging" : ""}`}
            onClick={(event) => event.stopPropagation()}
            onPointerDown={onStagePointerDown}
            onPointerMove={onStagePointerMove}
            onPointerUp={finishStageDrag}
            onPointerCancel={finishStageDrag}
            onPointerLeave={finishStageDrag}
            onWheel={(event) => {
              event.preventDefault();
              event.stopPropagation();
              updateZoom(scale + (event.deltaY < 0 ? SCALE_STEP : -SCALE_STEP), {
                x: event.clientX,
                y: event.clientY,
              });
            }}
          >
            <div
              className="asset-zoom-canvas"
              style={{
                width: zoomMetrics ? `${zoomMetrics.renderedWidth}px` : undefined,
                height: zoomMetrics ? `${zoomMetrics.renderedHeight}px` : undefined,
                transform: `translate3d(${imageLeft}px, ${imageTop}px, 0)`,
              }}
            >
              <img
                src={displayUrl ?? previewUrl}
                alt={alt}
                className="asset-zoom-image"
                draggable={false}
                onLoad={(event) => {
                  const image = event.currentTarget;
                  void resolveDisplayedImageDimensions(image).then((dimensions) => {
                    syncImageDimensions(dimensions);
                  });
                }}
                onDoubleClick={(event) => {
                  event.stopPropagation();
                  updateZoom(scale > 1 ? 1 : 2, {
                    x: event.clientX,
                    y: event.clientY,
                  });
                }}
              />
            </div>
            {scale > 1 && minimapSize && minimapViewport ? (
              <div
                ref={minimapRef}
                className={`asset-minimap ${isMinimapDragging ? "dragging" : ""}`}
                style={{
                  width: `${minimapSize.width}px`,
                  height: `${minimapSize.height}px`,
                }}
                onClick={(event) => event.stopPropagation()}
                onPointerDown={onMinimapPointerDown}
                onPointerMove={onMinimapPointerMove}
                onPointerUp={finishMinimapDrag}
                onPointerCancel={finishMinimapDrag}
                onPointerLeave={finishMinimapDrag}
              >
                <img
                  src={displayUrl ?? previewUrl}
                  alt=""
                  aria-hidden="true"
                  className="asset-minimap-image"
                  draggable={false}
                />
                <div
                  className="asset-minimap-viewport"
                  data-minimap-viewport="true"
                  style={{
                    width: `${minimapViewport.width}px`,
                    height: `${minimapViewport.height}px`,
                    left: `${minimapViewport.left}px`,
                    top: `${minimapViewport.top}px`,
                  }}
                />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
