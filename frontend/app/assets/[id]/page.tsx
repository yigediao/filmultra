import { notFound } from "next/navigation";

import { AssetDetailWorkspace } from "@/components/asset-detail-workspace";
import { getAsset, getPeople } from "@/lib/api";

type AssetPageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ ratings?: string | string[]; view?: string | string[] }>;
};

export default async function AssetPage({ params, searchParams }: AssetPageProps) {
  const { id } = await params;
  const query = searchParams ? await searchParams : undefined;
  const activeRatings = Array.isArray(query?.ratings) ? query?.ratings[0] : query?.ratings;
  const view = Array.isArray(query?.view) ? query?.view[0] : query?.view;
  const viewMode = view === "viewer" ? "viewer" : "details";
  const backHref = activeRatings ? `/?ratings=${activeRatings}` : "/";
  const navigationParams = new URLSearchParams();
  if (activeRatings) {
    navigationParams.set("ratings", activeRatings);
  }
  if (viewMode === "viewer") {
    navigationParams.set("view", "viewer");
  }
  const navigationQuery = navigationParams.toString() ? `?${navigationParams.toString()}` : "";
  const [asset, people] = await Promise.all([
    getAsset(id).catch(() => null),
    getPeople().catch(() => []),
  ]);

  if (!asset) {
    notFound();
  }

  return (
    <AssetDetailWorkspace
      asset={asset}
      people={people}
      backHref={backHref}
      navigationQuery={navigationQuery}
      viewMode={viewMode}
    />
  );
}
