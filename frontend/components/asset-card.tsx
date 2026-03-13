import Link from "next/link";

import { getPreviewUrl } from "@/lib/api";
import { AssetListItem } from "@/lib/types";

type AssetCardProps = {
  asset: AssetListItem;
};

export function AssetCard({ asset }: AssetCardProps) {
  const previewUrl = getPreviewUrl(asset.hero_preview_url);
  const ratingText = asset.rating > 0 ? `${asset.rating} / 5` : "Unrated";
  const captureDate = asset.capture_time
    ? new Date(asset.capture_time).toLocaleString("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Unknown capture time";

  return (
    <Link href={`/assets/${asset.id}?view=viewer`} className="asset-card">
      <div className="asset-thumb">
        {previewUrl ? (
          <img src={previewUrl} alt={asset.display_name} loading="lazy" />
        ) : (
          <div className="asset-thumb fallback">No Preview</div>
        )}
      </div>
      <div className="asset-meta">
        <div className="asset-topline">
          <h2>{asset.display_name}</h2>
          <span>{ratingText}</span>
        </div>
        <p>{captureDate}</p>
        <p>
          {asset.file_count} files
          {asset.camera_model ? ` · ${asset.camera_model}` : ""}
        </p>
        <p>{asset.people_count} people tagged</p>
      </div>
    </Link>
  );
}
