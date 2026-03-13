export type PhysicalFile = {
  id: number;
  file_path: string;
  directory_path: string;
  basename: string;
  extension: string;
  file_type: "RAW" | "JPG" | "XMP" | "OTHER";
  file_size: number;
  capture_time: string | null;
  width: number | null;
  height: number | null;
  is_hero: boolean;
  metadata_json: Record<string, unknown> | null;
};

export type Face = {
  id: number;
  logical_asset_id: number;
  physical_file_id: number;
  asset_display_name: string | null;
  face_index: number;
  bbox_x1: number;
  bbox_y1: number;
  bbox_x2: number;
  bbox_y2: number;
  confidence: number;
  cluster_id: string | null;
  person_id: number | null;
  person_name: string | null;
  preview_url: string | null;
  assignment_locked: boolean;
  is_excluded: boolean;
};

export type AssetPerson = {
  id: number;
  name: string;
  face_count: number;
  cover_preview_url: string | null;
};

export type BodyReconstruction = {
  id: number;
  logical_asset_id: number;
  face_id: number | null;
  person_id: number | null;
  person_name: string | null;
  job_id: number | null;
  status: string;
  overlay_url: string | null;
  mask_url: string | null;
  bundle_url: string | null;
  face_preview_url: string | null;
  mesh_object_urls: string[];
  result_json: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type BodyMaskCandidate = {
  index: number;
  score: number;
  overlay_url: string;
  mask_url: string;
};

export type BodyMaskEditPoint = {
  x: number;
  y: number;
};

export type BodyMaskEditStroke = {
  mode: "add" | "erase";
  radius: number;
  points: BodyMaskEditPoint[];
};

export type BodyReconstructionPreview = {
  preview_id: string;
  asset_id: number;
  face_id: number | null;
  source_image_url: string;
  face_preview_url: string | null;
  prompt_bbox: number[];
  image_width: number;
  image_height: number;
  selected_mask_index: number;
  candidates: BodyMaskCandidate[];
};

export type ObjectReconstructionPreview = {
  preview_id: string;
  asset_id: number;
  source_image_url: string;
  prompt_bbox: number[];
  image_width: number;
  image_height: number;
  selected_mask_index: number;
  candidates: BodyMaskCandidate[];
};

export type ObjectReconstruction = {
  id: number;
  logical_asset_id: number;
  job_id: number | null;
  status: string;
  overlay_url: string | null;
  mask_url: string | null;
  bundle_url: string | null;
  glb_url: string | null;
  glb_download_url: string | null;
  gaussian_ply_url: string | null;
  result_json: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type AssetListItem = {
  id: number;
  capture_key: string;
  display_name: string;
  rating: number;
  capture_time: string | null;
  camera_model: string | null;
  lens_model: string | null;
  width: number | null;
  height: number | null;
  file_count: number;
  hero_file_id: number | null;
  hero_preview_url: string | null;
  people_count: number;
};

export type AssetQuery = {
  limit?: number;
  offset?: number;
  ratings?: number[];
  rating?: number;
  ratingMin?: number;
  ratingMax?: number;
  unratedOnly?: boolean;
};

export type AssetDetail = {
  id: number;
  capture_key: string;
  display_name: string;
  rating: number;
  pick_flag: boolean;
  reject_flag: boolean;
  color_label: string | null;
  capture_time: string | null;
  camera_model: string | null;
  lens_model: string | null;
  width: number | null;
  height: number | null;
  hero_file_id: number | null;
  hero_preview_url: string | null;
  hero_display_url: string | null;
  hero_metadata: Record<string, unknown> | null;
  previous_asset_id: number | null;
  next_asset_id: number | null;
  physical_files: PhysicalFile[];
  people: AssetPerson[];
  faces: Face[];
  body_reconstructions: BodyReconstruction[];
  object_reconstructions: ObjectReconstruction[];
};

export type PersonListItem = {
  id: number;
  name: string;
  alias: string | null;
  notes: string | null;
  cover_face_id: number | null;
  cover_preview_url: string | null;
  asset_count: number;
  face_count: number;
  positive_training_samples: number;
  negative_training_samples: number;
  core_template_samples: number;
  support_template_samples: number;
  weak_template_samples: number;
  created_at: string;
  updated_at: string;
};

export type ClusterCandidate = {
  cluster_id: string;
  face_count: number;
  asset_count: number;
  sample_faces: Face[];
};

export type PersonDetail = PersonListItem & {
  assets: AssetListItem[];
  sample_faces: Face[];
  faces: Face[];
};

export type PersonReviewCandidate = {
  face: Face;
  decision_score: number;
  centroid_similarity: number;
  prototype_similarity: number;
  exemplar_similarity: number;
  negative_similarity: number | null;
  competitor_score: number | null;
  competitor_person_id: number | null;
  competitor_person_name: string | null;
  ambiguity: number;
  uncertainty: number;
  review_priority: number;
  auto_assign_eligible: boolean;
  current_assignment_name: string | null;
};

export type ReviewInboxItem = PersonReviewCandidate & {
  target_person_id: number;
  target_person_name: string;
  target_cover_preview_url: string | null;
};

export type JobRead = {
  id: number;
  job_type: "scan" | "metadata_sync" | "face_detect" | "recluster" | "sam3d_body" | "sam3d_object";
  status: "pending" | "running" | "completed" | "failed";
  payload_json: Record<string, unknown> | null;
  result_json: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AssetDownloadVariant = "JPG" | "RAW";

export type LibraryState = {
  total_assets: number;
  total_files: number;
  latest_asset_updated_at: string | null;
  active_scan_jobs: number;
  last_completed_scan_at: string | null;
};
