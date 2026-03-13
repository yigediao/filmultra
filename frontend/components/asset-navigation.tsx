"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

type AssetNavigationProps = {
  previousAssetId: number | null;
  nextAssetId: number | null;
  queryString?: string;
};

export function AssetNavigation({ previousAssetId, nextAssetId, queryString = "" }: AssetNavigationProps) {
  const router = useRouter();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey) {
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
      if (event.code === "Space") {
        event.preventDefault();
        if (event.shiftKey && previousAssetId !== null) {
          router.push(`/assets/${previousAssetId}${queryString}`);
        }
        if (!event.shiftKey && nextAssetId !== null) {
          router.push(`/assets/${nextAssetId}${queryString}`);
        }
        return;
      }
      if (event.key === "ArrowLeft" && previousAssetId !== null) {
        event.preventDefault();
        router.push(`/assets/${previousAssetId}${queryString}`);
      }
      if (event.key === "ArrowRight" && nextAssetId !== null) {
        event.preventDefault();
        router.push(`/assets/${nextAssetId}${queryString}`);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [nextAssetId, previousAssetId, queryString, router]);

  return (
    <div className="asset-navigation">
      {previousAssetId !== null ? (
        <Link href={`/assets/${previousAssetId}${queryString}`} className="asset-nav-link">
          ← 上一张
        </Link>
      ) : (
        <span className="asset-nav-link disabled">← 上一张</span>
      )}
      {nextAssetId !== null ? (
        <Link href={`/assets/${nextAssetId}${queryString}`} className="asset-nav-link">
          下一张 →
        </Link>
      ) : (
        <span className="asset-nav-link disabled">下一张 →</span>
      )}
    </div>
  );
}
