import Link from "next/link";

import { AssetGalleryShell } from "@/components/asset-gallery-shell";
import { LibraryLiveRefresh } from "@/components/library-live-refresh";
import { getAssets, getLibraryState } from "@/lib/api";

const ratingOptions = [
  {
    value: 0,
    label: "未评分",
    description: "0 星",
  },
  {
    value: 1,
    label: "1★",
    description: "只看 1 星",
  },
  {
    value: 2,
    label: "2★",
    description: "只看 2 星",
  },
  {
    value: 3,
    label: "3★",
    description: "只看 3 星",
  },
  {
    value: 4,
    label: "4★",
    description: "只看 4 星",
  },
  {
    value: 5,
    label: "5★",
    description: "只看 5 星",
  },
] as const;

type HomePageProps = {
  searchParams?: Promise<{ ratings?: string | string[]; view?: string | string[] }>;
};

function parseRatings(rawValue: string | string[] | undefined): number[] {
  const value = Array.isArray(rawValue) ? rawValue[0] : rawValue;
  if (!value) {
    return [];
  }

  const parsed = value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item >= 0 && item <= 5);

  return [...new Set(parsed)];
}

function buildRatingsQuery(selectedRatings: number[]): string {
  const searchParams = new URLSearchParams();
  if (selectedRatings.length > 0) {
    searchParams.set("ratings", selectedRatings.join(","));
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

function buildViewerQuery(selectedRatings: number[]): string {
  const searchParams = new URLSearchParams();
  if (selectedRatings.length === 0) {
    searchParams.set("view", "viewer");
    return `?${searchParams.toString()}`;
  }
  searchParams.set("ratings", selectedRatings.join(","));
  searchParams.set("view", "viewer");
  return `?${searchParams.toString()}`;
}

function toggleRatingSelection(selectedRatings: number[], rating: number): number[] {
  if (selectedRatings.includes(rating)) {
    return selectedRatings.filter((item) => item !== rating);
  }
  return [...selectedRatings, rating].sort((left, right) => left - right);
}

function summarizeRatings(selectedRatings: number[]): string {
  if (selectedRatings.length === 0) {
    return "全部评分";
  }

  return selectedRatings
    .map((rating) => (rating === 0 ? "未评分" : `${rating}★`))
    .join(" / ");
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = searchParams ? await searchParams : undefined;
  const activeRatings = parseRatings(params?.ratings);
  const [assets, libraryState] = await Promise.all([
    getAssets({
      limit: 240,
      ratings: activeRatings,
    }).catch(() => []),
    getLibraryState().catch(() => null),
  ]);
  const filterLinks = ratingOptions.map((option) => {
    const nextSelection = toggleRatingSelection(activeRatings, option.value);
    return {
      key: String(option.value),
      label: option.label,
      description: option.description,
      href: nextSelection.length === 0 ? "/" : buildRatingsQuery(nextSelection),
      active: activeRatings.includes(option.value),
    };
  });
  const assetLinkQuery = buildViewerQuery(activeRatings);
  const syncStatusLabel = libraryState?.active_scan_jobs ? "后台同步中" : "自动同步已开启";

  return (
    <main className="page-shell library-shell">
      {libraryState ? <LibraryLiveRefresh initialState={libraryState} /> : null}
      <section className="library-hero">
        <div className="library-hero-copy">
          <p className="eyebrow">Library View</p>
          <h1>按评分筛片</h1>
          <p className="library-copy">
            点击照片直接进入看片。评分支持多选并集，新照片进入文件夹或子文件夹后会自动入库并刷新时间线。
          </p>
          <div className="library-hero-actions">
            <Link href="/people" className="pill-link">
              人物工作区
            </Link>
            <span className={`library-sync-pill ${libraryState?.active_scan_jobs ? "active" : ""}`}>{syncStatusLabel}</span>
          </div>
        </div>
        <div className="library-stats">
          <div>
            <span className="stat-label">当前结果</span>
            <strong>{assets.length}</strong>
          </div>
          <div>
            <span className="stat-label">评分筛选</span>
            <strong>{summarizeRatings(activeRatings)}</strong>
          </div>
          <div>
            <span className="stat-label">同步状态</span>
            <strong>{syncStatusLabel}</strong>
          </div>
        </div>
      </section>

      {assets.length === 0 && activeRatings.length === 0 ? (
        <section className="empty-state">
          <h2>图库还没有扫描结果</h2>
          <p>
            先启动后端后调用 <code>POST /api/jobs/scan</code>，指定 NAS 挂载目录，就会建立第一批逻辑照片。
          </p>
        </section>
      ) : (
        <AssetGalleryShell
          assets={assets}
          filters={filterLinks}
          assetLinkQuery={assetLinkQuery}
          clearFilterHref="/"
          clearFilterVisible={activeRatings.length > 0}
        />
      )}
    </main>
  );
}
