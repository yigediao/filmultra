"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { downloadAssetsArchive, getPreviewUrl } from "@/lib/api";
import { AssetDownloadVariant, AssetListItem } from "@/lib/types";

type GalleryFilterLink = {
  key: string;
  label: string;
  description: string;
  href: string;
  active: boolean;
};

type AssetGalleryShellProps = {
  assets: AssetListItem[];
  filters: GalleryFilterLink[];
  assetLinkQuery?: string;
  clearFilterHref?: string;
  clearFilterVisible?: boolean;
};

type GalleryTile = {
  asset: AssetListItem;
  aspectRatio: number;
  width: number;
  height: number;
};

type GalleryRow = {
  height: number;
  items: GalleryTile[];
};

const GALLERY_GAP = 6;

function getAspectRatio(asset: AssetListItem): number {
  if (asset.width && asset.height && asset.width > 0 && asset.height > 0) {
    return Math.max(0.45, Math.min(3.8, asset.width / asset.height));
  }
  return 4 / 3;
}

function getTargetRowHeight(containerWidth: number): number {
  if (containerWidth < 460) {
    return 102;
  }
  if (containerWidth < 720) {
    return 118;
  }
  if (containerWidth < 1180) {
    return 156;
  }
  return 180;
}

function buildRow(
  items: Array<{ asset: AssetListItem; aspectRatio: number }>,
  containerWidth: number,
  targetRowHeight: number,
  isLastRow: boolean,
): GalleryRow {
  const availableWidth = containerWidth - GALLERY_GAP * Math.max(0, items.length - 1);
  const totalAspectRatio = items.reduce((sum, item) => sum + item.aspectRatio, 0);
  const justifiedHeight = availableWidth / totalAspectRatio;
  const rowHeight = isLastRow ? Math.min(targetRowHeight, justifiedHeight) : justifiedHeight;

  const tiles = items.map((item) => ({
    asset: item.asset,
    aspectRatio: item.aspectRatio,
    width: Math.max(72, Math.round(rowHeight * item.aspectRatio)),
    height: Math.max(72, Math.round(rowHeight)),
  }));

  if (!isLastRow && tiles.length > 0) {
    const usedWidth = tiles.reduce((sum, item) => sum + item.width, 0) + GALLERY_GAP * (tiles.length - 1);
    tiles[tiles.length - 1].width += containerWidth - usedWidth;
  }

  return {
    height: Math.max(72, Math.round(rowHeight)),
    items: tiles,
  };
}

function buildRows(assets: AssetListItem[], containerWidth: number): GalleryRow[] {
  if (containerWidth <= 0 || assets.length === 0) {
    return [];
  }

  const rows: GalleryRow[] = [];
  const currentRow: Array<{ asset: AssetListItem; aspectRatio: number }> = [];
  const targetRowHeight = getTargetRowHeight(containerWidth);
  let aspectSum = 0;

  assets.forEach((asset) => {
    const aspectRatio = getAspectRatio(asset);
    currentRow.push({ asset, aspectRatio });
    aspectSum += aspectRatio;

    const availableWidth = containerWidth - GALLERY_GAP * Math.max(0, currentRow.length - 1);
    const projectedHeight = availableWidth / aspectSum;
    const shouldFinalize = projectedHeight <= targetRowHeight || currentRow.length >= 12;

    if (!shouldFinalize) {
      return;
    }

    rows.push(buildRow(currentRow.splice(0), containerWidth, targetRowHeight, false));
    aspectSum = 0;
  });

  if (currentRow.length > 0) {
    rows.push(buildRow(currentRow, containerWidth, targetRowHeight, true));
  }

  return rows;
}

function formatCaptureDate(value: string | null): string {
  if (!value) {
    return "未记录时间";
  }

  return new Date(value).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AssetGalleryShell({
  assets,
  filters,
  assetLinkQuery = "",
  clearFilterHref = "/",
  clearFilterVisible = false,
}: AssetGalleryShellProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [measuredAspectRatios, setMeasuredAspectRatios] = useState<Record<number, number>>({});
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedAssetIds, setSelectedAssetIds] = useState<number[]>([]);
  const [downloadStatus, setDownloadStatus] = useState<string | null>(null);
  const [downloadVariant, setDownloadVariant] = useState<AssetDownloadVariant | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    function updateWidth() {
      const nextElement = containerRef.current;
      if (!nextElement) {
        return;
      }
      setContainerWidth(Math.floor(nextElement.clientWidth));
    }

    updateWidth();
    const observer = new ResizeObserver(() => {
      updateWidth();
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const visibleAssetIds = new Set(assets.map((asset) => asset.id));
    setSelectedAssetIds((current) => current.filter((assetId) => visibleAssetIds.has(assetId)));
  }, [assets]);

  const rows = useMemo(() => {
    const assetsWithMeasuredRatios = assets.map((asset) => ({
      ...asset,
      width: measuredAspectRatios[asset.id] ? measuredAspectRatios[asset.id] * 1000 : asset.width,
      height: measuredAspectRatios[asset.id] ? 1000 : asset.height,
    }));
    return buildRows(assetsWithMeasuredRatios, containerWidth);
  }, [assets, containerWidth, measuredAspectRatios]);

  function updateMeasuredAspectRatio(assetId: number, naturalWidth: number, naturalHeight: number) {
    if (naturalWidth <= 0 || naturalHeight <= 0) {
      return;
    }

    const nextRatio = naturalWidth / naturalHeight;
    setMeasuredAspectRatios((current) => {
      const previousRatio = current[assetId];
      if (previousRatio !== undefined && Math.abs(previousRatio - nextRatio) < 0.01) {
        return current;
      }
      return {
        ...current,
        [assetId]: nextRatio,
      };
    });
  }

  const allVisibleAssetIds = useMemo(() => assets.map((asset) => asset.id), [assets]);
  const allSelected = assets.length > 0 && selectedAssetIds.length === assets.length;

  function toggleSelectionMode() {
    setIsSelectionMode((current) => {
      const nextValue = !current;
      if (!nextValue) {
        setSelectedAssetIds([]);
        setDownloadStatus(null);
        setDownloadVariant(null);
      }
      return nextValue;
    });
  }

  function toggleSelection(assetId: number) {
    setSelectedAssetIds((current) =>
      current.includes(assetId) ? current.filter((item) => item !== assetId) : [...current, assetId],
    );
  }

  function toggleSelectAll() {
    setSelectedAssetIds(allSelected ? [] : allVisibleAssetIds);
  }

  async function runDownload(variant: AssetDownloadVariant) {
    if (selectedAssetIds.length === 0) {
      return;
    }

    try {
      setDownloadVariant(variant);
      setDownloadStatus(`正在准备 ${variant} 压缩包…`);
      const blob = await downloadAssetsArchive({
        assetIds: selectedAssetIds,
        variant,
      });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `filmultra-${variant.toLowerCase()}-selection.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
      setDownloadStatus(`已开始下载 ${variant} 压缩包。`);
    } catch {
      setDownloadStatus("下载失败，请检查后端日志。");
    } finally {
      setDownloadVariant(null);
    }
  }

  return (
    <section className="library-gallery-shell">
      <div className="library-filter-bar">
        <div className="library-filter-copy">
          <p className="eyebrow">Filter</p>
          <h2>按评分筛选</h2>
        </div>
        <div className="library-filter-panel">
          <div className="library-filter-pills">
            {clearFilterVisible ? (
              <Link href={clearFilterHref} className="library-filter-pill clear">
                <span>清空筛选</span>
                <small>显示全部评分</small>
              </Link>
            ) : null}
            {filters.map((filter) => (
              <Link
                key={filter.key}
                href={filter.href}
                className={`library-filter-pill ${filter.active ? "active" : ""}`}
                title={filter.description}
              >
                <span>{filter.label}</span>
                <small>{filter.description}</small>
              </Link>
            ))}
          </div>
          <div className="library-filter-actions">
            <button
              type="button"
              className={`pill-button ${isSelectionMode ? "accent" : ""}`}
              onClick={toggleSelectionMode}
            >
              {isSelectionMode ? "完成" : "选择"}
            </button>
          </div>
        </div>
      </div>

      {isSelectionMode ? (
        <div className="library-selection-bar">
          <div className="library-selection-copy">
            <p className="eyebrow">Selection</p>
            <h2>批量选择与下载</h2>
            <p className="muted-copy">
              已选 {selectedAssetIds.length} / {assets.length} 张
              {downloadStatus ? ` · ${downloadStatus}` : ""}
            </p>
          </div>
          <div className="library-selection-actions">
            <button type="button" className="pill-button" onClick={toggleSelectAll} disabled={assets.length === 0}>
              {allSelected ? "取消全选" : "全选当前结果"}
            </button>
            <button
              type="button"
              className="pill-button"
              onClick={() => setSelectedAssetIds([])}
              disabled={selectedAssetIds.length === 0}
            >
              清空选中
            </button>
            <button
              type="button"
              className="pill-button accent"
              onClick={() => void runDownload("JPG")}
              disabled={selectedAssetIds.length === 0 || downloadVariant !== null}
            >
              {downloadVariant === "JPG" ? "打包 JPG…" : "下载 JPG"}
            </button>
            <button
              type="button"
              className="pill-button accent"
              onClick={() => void runDownload("RAW")}
              disabled={selectedAssetIds.length === 0 || downloadVariant !== null}
            >
              {downloadVariant === "RAW" ? "打包 RAW…" : "下载 RAW"}
            </button>
            <button type="button" className="pill-button" onClick={toggleSelectionMode}>
              完成
            </button>
          </div>
        </div>
      ) : null}

      {assets.length === 0 ? (
        <div className="empty-state">
          <h3>当前筛选下没有照片</h3>
          <p>换一个评分档位，或者先回到详情页继续打分，这里会立刻更新。</p>
        </div>
      ) : (
        <div ref={containerRef} className="justified-gallery">
          {rows.map((row, rowIndex) => (
            <div key={`row-${rowIndex}`} className="justified-gallery-row" style={{ height: `${row.height}px` }}>
              {row.items.map((item) => {
                const previewUrl = getPreviewUrl(item.asset.hero_preview_url);
                const href = assetLinkQuery ? `/assets/${item.asset.id}${assetLinkQuery}` : `/assets/${item.asset.id}`;
                const isSelected = selectedAssetIds.includes(item.asset.id);

                return (
                  <div
                    key={item.asset.id}
                    className={`gallery-tile-shell ${isSelectionMode ? "selection-mode" : ""} ${isSelected ? "selected" : ""}`}
                    style={{ width: `${item.width}px`, height: `${item.height}px` }}
                  >
                    <Link
                      href={href}
                      className={`gallery-tile ${isSelectionMode ? "selectable" : ""}`}
                      onClick={(event) => {
                        if (!isSelectionMode) {
                          return;
                        }
                        event.preventDefault();
                        toggleSelection(item.asset.id);
                      }}
                    >
                      {previewUrl ? (
                        <img
                          src={previewUrl}
                          alt={item.asset.display_name}
                          loading="lazy"
                          onLoad={(event) => {
                            updateMeasuredAspectRatio(
                              item.asset.id,
                              event.currentTarget.naturalWidth,
                              event.currentTarget.naturalHeight,
                            );
                          }}
                        />
                      ) : (
                        <div className="gallery-tile-fallback">{item.asset.display_name}</div>
                      )}
                      <div className="gallery-tile-badges">
                        {item.asset.rating > 0 ? <span className="gallery-badge accent">{`${item.asset.rating}★`}</span> : null}
                        {item.asset.people_count > 0 ? <span className="gallery-badge">{`${item.asset.people_count} 人`}</span> : null}
                      </div>
                      <div className="gallery-tile-overlay">
                        <strong>{item.asset.display_name}</strong>
                        <span>{formatCaptureDate(item.asset.capture_time)}</span>
                      </div>
                    </Link>
                    {isSelectionMode ? (
                      <button
                        type="button"
                        className={`gallery-select-button ${isSelected ? "selected" : ""}`}
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          toggleSelection(item.asset.id);
                        }}
                        aria-pressed={isSelected}
                        aria-label={isSelected ? `取消选中 ${item.asset.display_name}` : `选中 ${item.asset.display_name}`}
                      >
                        {isSelected ? "✓" : ""}
                      </button>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
