"use client";

import { startTransition, useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";

import { getLibraryState } from "@/lib/api";
import { LibraryState } from "@/lib/types";

type LibraryLiveRefreshProps = {
  initialState: LibraryState;
  pollIntervalMs?: number;
};

function buildDataSignature(state: LibraryState): string {
  return [
    state.total_assets,
    state.total_files,
    state.latest_asset_updated_at ?? "",
  ].join(":");
}

export function LibraryLiveRefresh({
  initialState,
  pollIntervalMs = 5000,
}: LibraryLiveRefreshProps) {
  const router = useRouter();
  const initialSignature = useMemo(() => buildDataSignature(initialState), [initialState]);
  const signatureRef = useRef(initialSignature);

  useEffect(() => {
    signatureRef.current = initialSignature;
  }, [initialSignature]);

  useEffect(() => {
    let cancelled = false;

    async function pollLibraryState() {
      try {
        const nextState = await getLibraryState();
        if (cancelled) {
          return;
        }

        const nextSignature = buildDataSignature(nextState);
        if (nextSignature === signatureRef.current) {
          return;
        }

        signatureRef.current = nextSignature;
        startTransition(() => {
          router.refresh();
        });
      } catch {
        // Silent retry on the next interval keeps the page resilient while the backend restarts.
      }
    }

    const intervalId = window.setInterval(() => {
      void pollLibraryState();
    }, pollIntervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [pollIntervalMs, router]);

  return null;
}
