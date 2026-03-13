import {
  AssetDetail,
  AssetDownloadVariant,
  BodyMaskEditStroke,
  BodyReconstructionPreview,
  BodyReconstruction,
  ObjectReconstruction,
  ObjectReconstructionPreview,
  AssetQuery,
  AssetListItem,
  ClusterCandidate,
  JobRead,
  LibraryState,
  PersonDetail,
  PersonListItem,
  PersonReviewCandidate,
  ReviewInboxItem,
} from "@/lib/types";

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

function resolveApiBase(): string {
  if (typeof window === "undefined") {
    return apiBase;
  }

  const configuredUrl = new URL(apiBase);
  const browserHost = window.location.hostname;
  if (!browserHost || browserHost === "127.0.0.1" || browserHost === "localhost") {
    return configuredUrl.toString().replace(/\/$/, "");
  }

  if (configuredUrl.hostname === "127.0.0.1" || configuredUrl.hostname === "localhost") {
    configuredUrl.hostname = browserHost;
  }
  return configuredUrl.toString().replace(/\/$/, "");
}

export function getApiBase(): string {
  return resolveApiBase();
}

export function buildApiUrl(path: string): string {
  return `${resolveApiBase()}${path}`;
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function requestWithBody<T>(path: string, method: string, body: object): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function buildQuery(params: Record<string, string | number | boolean | number[] | null | undefined>): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) {
      return;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        return;
      }
      searchParams.set(key, value.join(","));
      return;
    }
    searchParams.set(key, String(value));
  });

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export async function getAssets(query: AssetQuery = {}): Promise<AssetListItem[]> {
  return request<AssetListItem[]>(
    `/api/assets${buildQuery({
      limit: query.limit,
      offset: query.offset,
      ratings: query.ratings,
      rating: query.rating,
      rating_min: query.ratingMin,
      rating_max: query.ratingMax,
      unrated_only: query.unratedOnly,
    })}`,
  );
}

export async function getAsset(assetId: string): Promise<AssetDetail> {
  return request<AssetDetail>(`/api/assets/${assetId}`);
}

export async function getLibraryState(): Promise<LibraryState> {
  return request<LibraryState>("/api/assets/state");
}

export async function getJob(jobId: number): Promise<JobRead> {
  return request<JobRead>(`/api/jobs/${jobId}`);
}

export async function getPeople(): Promise<PersonListItem[]> {
  return request<PersonListItem[]>("/api/people");
}

export async function getClusters(): Promise<ClusterCandidate[]> {
  return request<ClusterCandidate[]>("/api/people/clusters");
}

export async function getPerson(personId: string): Promise<PersonDetail> {
  return request<PersonDetail>(`/api/people/${personId}`);
}

export async function getPersonReviewCandidates(personId: string, limit = 18): Promise<PersonReviewCandidate[]> {
  return request<PersonReviewCandidate[]>(`/api/people/${personId}/review-candidates?limit=${limit}`);
}

export async function getReviewInbox(limit = 30): Promise<ReviewInboxItem[]> {
  return request<ReviewInboxItem[]>(`/api/people/review-inbox?limit=${limit}`);
}

export async function createPersonFromCluster(payload: {
  name: string;
  cluster_id: string;
}): Promise<PersonListItem> {
  return requestWithBody<PersonListItem>("/api/people", "POST", payload);
}

export async function updatePerson(
  personId: number,
  payload: { name?: string; alias?: string | null; notes?: string | null },
): Promise<PersonListItem> {
  return requestWithBody<PersonListItem>(`/api/people/${personId}`, "PATCH", payload);
}

export async function mergePeople(payload: {
  target_person_id: number;
  source_person_ids: number[];
}): Promise<PersonListItem> {
  return requestWithBody<PersonListItem>("/api/people/merge", "POST", payload);
}

export async function updateFaceAssignment(
  faceId: number,
  payload: { action: "assign_person" | "unassign" | "restore_auto"; person_id?: number },
) {
  return requestWithBody(`/api/faces/${faceId}/assignment`, "PATCH", payload);
}

export async function reviewPersonCandidate(
  personId: number,
  payload: { face_id: number; action: "confirm" | "reject" | "skip" },
) {
  return requestWithBody(`/api/people/${personId}/review-feedback`, "POST", payload);
}

export async function triggerFaceDetect(assetIds?: number[]) {
  return requestWithBody<JobRead>("/api/jobs/face-detect", "POST", { asset_ids: assetIds ?? null });
}

export async function triggerRecluster() {
  return requestWithBody<JobRead>("/api/jobs/recluster", "POST", {});
}

export async function triggerSam3dBody(payload: {
  assetId: number;
  faceId?: number;
  bodyBbox?: number[];
  maskIndex?: number;
  previewId?: string;
  maskEdits?: BodyMaskEditStroke[];
}) {
  return requestWithBody<JobRead>("/api/jobs/sam3d-body", "POST", {
    asset_id: payload.assetId,
    face_id: payload.faceId ?? null,
    body_bbox: payload.bodyBbox ?? null,
    mask_index: payload.maskIndex ?? null,
    preview_id: payload.previewId ?? null,
    mask_edits: payload.maskEdits ?? null,
  });
}

export async function getBodyReconstruction(reconstructionId: number): Promise<BodyReconstruction> {
  return request<BodyReconstruction>(`/api/body3d/${reconstructionId}`);
}

export async function previewBodyMask(payload: {
  assetId: number;
  faceId?: number;
  bodyBbox?: number[];
  maskIndex?: number;
}) {
  return requestWithBody<BodyReconstructionPreview>("/api/body3d/preview-mask", "POST", {
    asset_id: payload.assetId,
    face_id: payload.faceId ?? null,
    body_bbox: payload.bodyBbox ?? null,
    mask_index: payload.maskIndex ?? null,
  });
}

export async function triggerSam3dObject(payload: {
  assetId: number;
  objectBbox: number[];
  maskIndex?: number;
  previewId?: string;
  maskEdits?: BodyMaskEditStroke[];
}) {
  return requestWithBody<JobRead>("/api/jobs/sam3d-object", "POST", {
    asset_id: payload.assetId,
    object_bbox: payload.objectBbox,
    mask_index: payload.maskIndex ?? null,
    preview_id: payload.previewId ?? null,
    mask_edits: payload.maskEdits ?? null,
  });
}

export async function previewObjectMask(payload: {
  assetId: number;
  objectBbox: number[];
  maskIndex?: number;
}) {
  return requestWithBody<ObjectReconstructionPreview>("/api/object3d/preview-mask", "POST", {
    asset_id: payload.assetId,
    object_bbox: payload.objectBbox,
    mask_index: payload.maskIndex ?? null,
  });
}

export async function getObjectReconstruction(reconstructionId: number): Promise<ObjectReconstruction> {
  return request<ObjectReconstruction>(`/api/object3d/${reconstructionId}`);
}

export async function downloadAssetsArchive(payload: { assetIds: number[]; variant: AssetDownloadVariant }) {
  const response = await fetch(buildApiUrl("/api/assets/download"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      asset_ids: payload.assetIds,
      variant: payload.variant,
    }),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.blob();
}

export function buildAssetDownloadUrl(assetId: number, variant: AssetDownloadVariant): string {
  return buildApiUrl(`/api/assets/${assetId}/download-file?variant=${variant}`);
}

export async function downloadAssetFile(assetId: number, variant: AssetDownloadVariant) {
  const response = await fetch(buildAssetDownloadUrl(assetId, variant), {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  const disposition = response.headers.get("Content-Disposition");
  const filenameMatch = disposition?.match(/filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?/i);
  const encodedFilename = filenameMatch?.[1];
  const fallbackFilename = filenameMatch?.[2];

  return {
    blob: await response.blob(),
    filename: encodedFilename
      ? decodeURIComponent(encodedFilename)
      : fallbackFilename ?? `filmultra-${assetId}.${variant.toLowerCase()}`,
  };
}

export function getPreviewUrl(path: string | null): string | null {
  return path ? buildApiUrl(path) : null;
}
