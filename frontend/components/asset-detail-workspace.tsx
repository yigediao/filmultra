"use client";

import Link from "next/link";
import { TouchEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AssetNavigation } from "@/components/asset-navigation";
import { BodyReconstructionPanel } from "@/components/body-reconstruction-panel";
import { ObjectReconstructionPanel } from "@/components/object-reconstruction-panel";
import { AssetViewer } from "@/components/asset-viewer";
import { FaceReviewCard } from "@/components/face-review-card";
import { useAssetWorkspacePreferences } from "@/components/asset-workspace-preferences";
import { RatingControl } from "@/components/rating-control";
import { downloadAssetFile, getPreviewUrl } from "@/lib/api";
import { AssetDetail, AssetDownloadVariant, PersonListItem } from "@/lib/types";

type AssetDetailWorkspaceProps = {
  asset: AssetDetail;
  people: PersonListItem[];
  backHref?: string;
  navigationQuery?: string;
  viewMode?: "viewer" | "details";
};

const metadataLabels: Record<string, string> = {
  camera_make: "品牌",
  camera_model: "机身",
  lens_model: "镜头",
  date_time_original: "拍摄时间",
  aperture: "光圈",
  exposure_time: "快门",
  iso: "ISO",
  focal_length: "焦距",
  exposure_bias: "曝光补偿",
  flash: "闪光灯",
  metering_mode: "测光模式",
  white_balance: "白平衡",
  exposure_program: "曝光程序",
  exposure_mode: "曝光模式",
  software: "软件",
  lens_serial_number: "镜头序列号",
  lens_specification: "镜头规格",
  capture_time_source: "时间来源",
};

const metadataOrder = [
  "camera_make",
  "camera_model",
  "lens_model",
  "date_time_original",
  "aperture",
  "exposure_time",
  "iso",
  "focal_length",
  "exposure_bias",
  "flash",
  "metering_mode",
  "white_balance",
  "exposure_program",
  "exposure_mode",
  "software",
  "lens_serial_number",
  "lens_specification",
  "capture_time_source",
];

const exifSummaryKeys = [
  "aperture",
  "exposure_time",
  "iso",
  "focal_length",
  "exposure_bias",
  "white_balance",
];

type MobileSheetMode = "info" | "rating" | null;

export function AssetDetailWorkspace({
  asset,
  people,
  backHref = "/",
  navigationQuery = "",
  viewMode = "details",
}: AssetDetailWorkspaceProps) {
  const router = useRouter();
  const {
    immersive,
    setImmersive,
    sidebarCollapsed,
    setSidebarCollapsed,
    exifExpanded,
    setExifExpanded,
  } = useAssetWorkspacePreferences();
  const [currentRating, setCurrentRating] = useState(asset.rating);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const [mobileSheet, setMobileSheet] = useState<MobileSheetMode>(null);
  const [mobileDownloadVariant, setMobileDownloadVariant] = useState<AssetDownloadVariant | null>(null);
  const swipeStartRef = useRef<{ x: number; y: number } | null>(null);
  const detailSearchParams = new URLSearchParams(navigationQuery.replace(/^\?/, ""));
  detailSearchParams.delete("view");
  const normalizedDetailQuery = detailSearchParams.toString() ? `?${detailSearchParams.toString()}` : "";
  const viewerQuery = (() => {
    const searchParams = new URLSearchParams(navigationQuery.replace(/^\?/, ""));
    searchParams.set("view", "viewer");
    const query = searchParams.toString();
    return query ? `?${query}` : "?view=viewer";
  })();
  const detailHref = `/assets/${asset.id}${normalizedDetailQuery}`;
  const viewerHref = `/assets/${asset.id}${viewerQuery}`;
  const effectiveSidebarHidden = immersive || sidebarCollapsed;
  const previewUrl = getPreviewUrl(asset.hero_preview_url);
  const displayUrl = getPreviewUrl(asset.hero_display_url);
  const heroMetadata = asset.hero_metadata ?? {};
  const metadataEntries = [
    ...metadataOrder
      .map((key) => ({
        key,
        label: metadataLabels[key] ?? key,
        value: heroMetadata[key],
      }))
      .filter((item) => item.value !== null && item.value !== undefined && item.value !== ""),
    ...Object.entries(heroMetadata)
      .filter(([key, value]) => !metadataOrder.includes(key) && value !== null && value !== undefined && value !== "")
      .map(([key, value]) => ({
        key,
        label: metadataLabels[key] ?? key,
        value,
      })),
  ];
  const exifSummaryEntries = exifSummaryKeys
    .map((key) => metadataEntries.find((item) => item.key === key))
    .filter((item): item is (typeof metadataEntries)[number] => Boolean(item));
  const compactMetadataEntries = exifSummaryEntries.length > 0 ? exifSummaryEntries : metadataEntries.slice(0, 6);
  const hiddenMetadataCount = Math.max(0, metadataEntries.length - compactMetadataEntries.length);
  const isMobileViewer = isMobileViewport && viewMode === "viewer";

  useEffect(() => {
    setCurrentRating(asset.rating);
  }, [asset.rating]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const mediaQuery = window.matchMedia("(max-width: 960px)");
    const updateViewportMode = () => {
      setIsMobileViewport(mediaQuery.matches);
    };

    updateViewportMode();
    mediaQuery.addEventListener("change", updateViewportMode);

    return () => {
      mediaQuery.removeEventListener("change", updateViewportMode);
    };
  }, []);

  useEffect(() => {
    if (viewMode === "viewer") {
      setImmersive(true);
      setSidebarCollapsed(true);
      return;
    }
    setImmersive(false);
    setSidebarCollapsed(false);
  }, [setImmersive, setSidebarCollapsed, viewMode]);

  useEffect(() => {
    if (!isMobileViewer) {
      setMobileSheet(null);
    }
  }, [isMobileViewer]);

  useEffect(() => {
    setMobileDownloadVariant(null);
  }, [asset.id]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A"].includes(target.tagName) || target.isContentEditable)
      ) {
        return;
      }
      if (document.body.dataset.assetZoomOpen === "true") {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "i") {
        if (viewMode === "viewer") {
          event.preventDefault();
          if (isMobileViewer) {
            setMobileSheet((current) => (current === "info" ? null : "info"));
          } else {
            router.push(detailHref);
          }
          return;
        }
        event.preventDefault();
        setSidebarCollapsed((current) => !current);
      }
      if (key === "f") {
        event.preventDefault();
        router.push(immersive ? detailHref : viewerHref);
      }
      if (event.key === "Escape" && immersive) {
        event.preventDefault();
        router.push(detailHref);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [detailHref, immersive, isMobileViewer, router, setImmersive, setSidebarCollapsed, viewMode, viewerHref]);

  function pushAsset(assetId: number | null) {
    if (assetId === null) {
      return;
    }
    router.push(`/assets/${assetId}${navigationQuery}`);
  }

  async function runAssetDownload(variant: AssetDownloadVariant) {
    try {
      setMobileDownloadVariant(variant);
      const { blob, filename } = await downloadAssetFile(asset.id, variant);
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch {
      window.alert(`${variant} 下载失败，请检查后端服务。`);
    } finally {
      setMobileDownloadVariant(null);
    }
  }

  function handlePreviewTouchStart(event: TouchEvent<HTMLElement>) {
    if (!isMobileViewer || document.body.dataset.assetZoomOpen === "true") {
      return;
    }
    const touch = event.changedTouches[0];
    swipeStartRef.current = {
      x: touch.clientX,
      y: touch.clientY,
    };
  }

  function handlePreviewTouchEnd(event: TouchEvent<HTMLElement>) {
    if (!isMobileViewer || document.body.dataset.assetZoomOpen === "true") {
      swipeStartRef.current = null;
      return;
    }

    const swipeStart = swipeStartRef.current;
    swipeStartRef.current = null;
    if (!swipeStart) {
      return;
    }

    const touch = event.changedTouches[0];
    const deltaX = touch.clientX - swipeStart.x;
    const deltaY = touch.clientY - swipeStart.y;
    if (Math.abs(deltaY) > Math.abs(deltaX) * 1.2 && Math.abs(deltaY) > 84) {
      if (deltaY > 0) {
        router.push(backHref);
        return;
      }
      setMobileSheet("info");
      return;
    }

    if (Math.abs(deltaY) > 48 || Math.abs(deltaX) < 54) {
      return;
    }

    if (deltaX < 0) {
      pushAsset(asset.next_asset_id);
      return;
    }
    pushAsset(asset.previous_asset_id);
  }

  function toggleMobileSheet(nextSheet: Exclude<MobileSheetMode, null>) {
    setMobileSheet((current) => (current === nextSheet ? null : nextSheet));
  }

  return (
    <main className={`page-shell detail-shell asset-workspace ${immersive ? "immersive" : ""} ${isMobileViewer ? "mobile-viewer" : ""}`}>
      <div className={`detail-header ${immersive ? "hidden" : ""}`}>
        <Link href={backHref} className="back-link">
          Back to grid
        </Link>
        <div>
          <p className="eyebrow">Logical Asset</p>
          <h1>{asset.display_name}</h1>
        </div>
      </div>

      {isMobileViewer ? (
        <section className="asset-mobile-topbar">
          <Link href={backHref} className="asset-mobile-top-action">
            图库
          </Link>
          <div className="asset-mobile-top-meta">
            <strong>{asset.display_name}</strong>
            <span>{currentRating > 0 ? `${currentRating}★ · 左右切图` : "左右切图 · 下滑返回"}</span>
          </div>
          <div className="asset-mobile-top-actions">
            <button
              type="button"
              className="asset-mobile-top-action"
              onClick={() => void runAssetDownload("JPG")}
              disabled={mobileDownloadVariant !== null}
            >
              {mobileDownloadVariant === "JPG" ? "下载中" : "下载 JPG"}
            </button>
          </div>
        </section>
      ) : null}

      <section className={`asset-workspace-toolbar ${isMobileViewer ? "mobile-hidden" : ""}`}>
        <div className="asset-toolbar-meta">
          <Link href={backHref} className="asset-toolbar-back">
            返回网格
          </Link>
          <div>
            <strong>{asset.display_name}</strong>
            <p className="muted-copy">
              {immersive
                ? "`Space` 下一张 · `Shift + Space` 上一张 · `I` 详细信息 · `Esc` 退出"
                : "`Space` 下一张 · `Shift + Space` 上一张 · `I` 信息栏 · `F` 沉浸模式"}
            </p>
          </div>
        </div>
        <div className="asset-toolbar-actions">
          <div className={`asset-rating-indicator ${immersive ? "immersive" : ""}`}>
            <span className="asset-rating-label">当前评分</span>
            <strong>{currentRating > 0 ? `${currentRating} 星` : "未评分"}</strong>
            <span className="asset-rating-stars" aria-hidden="true">
              {Array.from({ length: 5 }, (_, index) => (index < currentRating ? "★" : "☆")).join("")}
            </span>
          </div>
          <AssetNavigation
            previousAssetId={asset.previous_asset_id}
            nextAssetId={asset.next_asset_id}
            queryString={navigationQuery}
          />
          {immersive ? (
            <button type="button" className="pill-button" onClick={() => router.push(detailHref)}>
              详细信息
            </button>
          ) : (
            <button
              type="button"
              className="pill-button"
              onClick={() => setSidebarCollapsed((current) => !current)}
            >
              {effectiveSidebarHidden ? "显示信息" : "收起信息"}
            </button>
          )}
          {!immersive ? (
            <button type="button" className="pill-button accent" onClick={() => router.push(viewerHref)}>
              沉浸看片
            </button>
          ) : null}
        </div>
      </section>

      <section className={`detail-layout ${effectiveSidebarHidden ? "focus" : ""}`}>
        <div className="detail-preview" onTouchStart={handlePreviewTouchStart} onTouchEnd={handlePreviewTouchEnd}>
          <AssetViewer
            previewUrl={previewUrl}
            displayUrl={displayUrl}
            alt={asset.display_name}
            width={asset.width}
            height={asset.height}
          />
        </div>

        <aside className={`detail-panel ${effectiveSidebarHidden ? "hidden" : ""}`}>
          <div className="detail-card">
            <span className="stat-label">Rating</span>
            <RatingControl assetId={asset.id} rating={asset.rating} onRatingChange={setCurrentRating} />
          </div>
          <div className="detail-card">
            <span className="stat-label">Capture</span>
            <strong>
              {asset.capture_time
                ? new Date(asset.capture_time).toLocaleString("zh-CN", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })
                : "Unknown"}
            </strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Camera</span>
            <strong>{asset.camera_model ?? "Unknown"}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Lens</span>
            <strong>{asset.lens_model ?? "Unknown"}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Dimensions</span>
            <strong>
              {asset.width && asset.height ? `${asset.width} × ${asset.height}` : "Pending"}
            </strong>
          </div>
        </aside>
      </section>

      {isMobileViewer ? (
        <>
          <div className="asset-mobile-bottom-bar">
            <button
              type="button"
              className="asset-mobile-action"
              onClick={() => pushAsset(asset.previous_asset_id)}
              disabled={asset.previous_asset_id === null}
            >
              <span>上一张</span>
            </button>
            <button
              type="button"
              className={`asset-mobile-action ${mobileSheet === "rating" ? "active" : ""}`}
              onClick={() => toggleMobileSheet("rating")}
            >
              <span>{currentRating > 0 ? `${currentRating}★` : "评分"}</span>
            </button>
            <button
              type="button"
              className={`asset-mobile-action ${mobileSheet === "info" ? "active" : ""}`}
              onClick={() => toggleMobileSheet("info")}
            >
              <span>信息</span>
            </button>
            <button
              type="button"
              className="asset-mobile-action"
              onClick={() => pushAsset(asset.next_asset_id)}
              disabled={asset.next_asset_id === null}
            >
              <span>下一张</span>
            </button>
          </div>

          {mobileSheet ? (
            <div className="asset-mobile-sheet-scrim" onClick={() => setMobileSheet(null)}>
              <section className="asset-mobile-sheet" onClick={(event) => event.stopPropagation()}>
                <div className="asset-mobile-sheet-handle" />
                <div className="asset-mobile-sheet-header">
                  <div>
                    <p className="eyebrow">{mobileSheet === "rating" ? "Rating" : "Info"}</p>
                    <h2>{mobileSheet === "rating" ? "快速评分" : "照片信息"}</h2>
                  </div>
                  <button type="button" className="pill-button" onClick={() => setMobileSheet(null)}>
                    关闭
                  </button>
                </div>

                {mobileSheet === "rating" ? (
                  <div className="asset-mobile-sheet-body">
                    <RatingControl assetId={asset.id} rating={asset.rating} onRatingChange={setCurrentRating} />
                  </div>
                ) : (
                  <div className="asset-mobile-sheet-body">
                    <div className="asset-mobile-quick-facts">
                      <div className="metadata-row compact">
                        <span>拍摄时间</span>
                        <strong>
                          {asset.capture_time
                            ? new Date(asset.capture_time).toLocaleString("zh-CN", {
                                dateStyle: "medium",
                                timeStyle: "short",
                              })
                            : "Unknown"}
                        </strong>
                      </div>
                      <div className="metadata-row compact">
                        <span>机身</span>
                        <strong>{asset.camera_model ?? "Unknown"}</strong>
                      </div>
                      <div className="metadata-row compact">
                        <span>镜头</span>
                        <strong>{asset.lens_model ?? "Unknown"}</strong>
                      </div>
                      <div className="metadata-row compact">
                        <span>尺寸</span>
                        <strong>{asset.width && asset.height ? `${asset.width} × ${asset.height}` : "Pending"}</strong>
                      </div>
                    </div>
                    {compactMetadataEntries.length > 0 ? (
                      <div className="metadata-summary-grid">
                        {compactMetadataEntries.map((item) => (
                          <div key={item.key} className="metadata-row compact">
                            <span>{item.label}</span>
                            <strong>{String(item.value)}</strong>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    <div className="asset-mobile-sheet-actions">
                      <button
                        type="button"
                        className="pill-button accent"
                        onClick={() => void runAssetDownload("JPG")}
                        disabled={mobileDownloadVariant !== null}
                      >
                        {mobileDownloadVariant === "JPG" ? "正在下载 JPG…" : "下载 JPG"}
                      </button>
                      <Link href={detailHref} className="pill-link">
                        打开完整详情
                      </Link>
                    </div>
                  </div>
                )}
              </section>
            </div>
          ) : null}
        </>
      ) : null}

      <section className={`section-block asset-secondary-section ${immersive ? "hidden" : ""}`}>
        <div className="section-header">
          <div>
            <p className="eyebrow">Camera EXIF</p>
            <h2>拍摄参数</h2>
          </div>
          {metadataEntries.length > 0 ? (
            <button type="button" className="pill-button" onClick={() => setExifExpanded((current) => !current)}>
              {exifExpanded ? "收起完整 EXIF" : hiddenMetadataCount > 0 ? `展开完整 EXIF（+${hiddenMetadataCount}）` : "完整 EXIF"}
            </button>
          ) : null}
        </div>
        {metadataEntries.length === 0 ? (
          <div className="empty-state">
            <h3>当前还没有可展示的 EXIF</h3>
            <p>如果你刚升级到这版，重新扫描一次目录后，这里的机身和曝光参数会完整得多。</p>
          </div>
        ) : (
          <div className="exif-panel">
            <div className="metadata-summary-grid">
              {compactMetadataEntries.map((item) => (
                <div key={item.key} className="metadata-row compact">
                  <span>{item.label}</span>
                  <strong>{String(item.value)}</strong>
                </div>
              ))}
            </div>
            {!exifExpanded && hiddenMetadataCount > 0 ? (
              <p className="muted-copy exif-summary-note">
                默认只显示常用参数，另外还有 {hiddenMetadataCount} 项完整 EXIF 已折叠。
              </p>
            ) : null}
            {exifExpanded ? (
              <div className="metadata-grid">
                {metadataEntries.map((item) => (
                  <div key={item.key} className="metadata-row">
                    <span>{item.label}</span>
                    <strong>{String(item.value)}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </section>

      <section className={`files-panel asset-secondary-section ${immersive ? "hidden" : ""}`}>
        <div className="files-header">
          <p className="eyebrow">Physical Files</p>
          <h2>{asset.physical_files.length} linked files</h2>
        </div>
        <div className="file-table">
          {asset.physical_files.map((file) => (
            <div key={file.id} className="file-row">
              <div>
                <strong>{file.basename + file.extension}</strong>
                <p>{file.file_path}</p>
              </div>
              <div>
                <strong>{file.file_type}</strong>
                <p>
                  {Math.round(file.file_size / 1024)} KB
                  {file.width && file.height ? ` · ${file.width} × ${file.height}` : ""}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className={`section-block asset-secondary-section ${immersive ? "hidden" : ""}`}>
        <BodyReconstructionPanel
          assetId={asset.id}
          heroPreviewUrl={asset.hero_preview_url}
          faces={asset.faces}
          reconstructions={asset.body_reconstructions}
        />
      </section>

      <section className={`section-block asset-secondary-section ${immersive ? "hidden" : ""}`}>
        <ObjectReconstructionPanel
          assetId={asset.id}
          heroPreviewUrl={asset.hero_preview_url}
          reconstructions={asset.object_reconstructions}
        />
      </section>

      <section className={`section-block asset-secondary-section ${immersive ? "hidden" : ""}`}>
        <div className="section-header">
          <div>
            <p className="eyebrow">People</p>
            <h2>识别到的人物</h2>
          </div>
        </div>
        {asset.people.length === 0 ? (
          <div className="empty-state">
            <h3>这张照片还没有人物归类</h3>
            <p>先到人物页运行 Detect Faces，再回到这里查看识别结果。</p>
          </div>
        ) : (
          <div className="people-grid compact">
            {asset.people.map((person) => {
              const coverUrl = getPreviewUrl(person.cover_preview_url);
              return (
                <Link key={person.id} href={`/people/${person.id}`} className="person-card compact">
                  <div className="person-cover">
                    {coverUrl ? <img src={coverUrl} alt={person.name} /> : <div className="asset-thumb fallback">No Face</div>}
                  </div>
                  <div className="person-meta">
                    <div className="asset-topline">
                      <h3>{person.name}</h3>
                      <span>{person.face_count}</span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      <section className={`section-block asset-secondary-section ${immersive ? "hidden" : ""}`}>
        <div className="section-header">
          <div>
            <p className="eyebrow">Faces</p>
            <h2>人脸样本</h2>
          </div>
        </div>
        {asset.faces.length === 0 ? (
          <div className="empty-state">
            <h3>还没有检测到人脸</h3>
            <p>当前照片还没有跑到人物识别流程。</p>
          </div>
        ) : (
          <div className="face-review-grid">
            {asset.faces.map((face) => (
              <FaceReviewCard key={face.id} face={face} people={people} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
