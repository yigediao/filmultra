import Link from "next/link";
import { notFound } from "next/navigation";

import { FaceReviewCard } from "@/components/face-review-card";
import { MergePeopleForm } from "@/components/merge-people-form";
import { PersonEditForm } from "@/components/person-edit-form";
import { ReviewCandidateCard } from "@/components/review-candidate-card";
import { AssetCard } from "@/components/asset-card";
import { getPeople, getPerson, getPersonReviewCandidates, getPreviewUrl } from "@/lib/api";

type PersonPageProps = {
  params: Promise<{ id: string }>;
};

export default async function PersonPage({ params }: PersonPageProps) {
  const { id } = await params;
  const [person, people, reviewCandidates] = await Promise.all([
    getPerson(id).catch(() => null),
    getPeople().catch(() => []),
    getPersonReviewCandidates(id).catch(() => []),
  ]);

  if (!person) {
    notFound();
  }

  const coverUrl = getPreviewUrl(person.cover_preview_url);

  return (
    <main className="page-shell people-shell">
      <div className="detail-header">
        <Link href="/people" className="back-link">
          Back to people
        </Link>
        <div>
          <p className="eyebrow">Person Detail</p>
          <h1>{person.name}</h1>
        </div>
      </div>

      <section className="detail-layout">
        <div className="detail-preview">
          {coverUrl ? (
            <img src={coverUrl} alt={person.name} />
          ) : (
            <div className="asset-thumb fallback large">No Face Preview</div>
          )}
        </div>
        <aside className="detail-panel">
          <div className="detail-card">
            <span className="stat-label">Manage</span>
            <PersonEditForm personId={person.id} initialName={person.name} />
          </div>
          <div className="detail-card">
            <span className="stat-label">Merge</span>
            <MergePeopleForm currentPersonId={person.id} people={people} />
          </div>
          <div className="detail-card">
            <span className="stat-label">Assets</span>
            <strong>{person.asset_count}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Faces</span>
            <strong>{person.face_count}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Positive Samples</span>
            <strong>{person.positive_training_samples}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Negative Samples</span>
            <strong>{person.negative_training_samples}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Core Templates</span>
            <strong>{person.core_template_samples}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Support Templates</span>
            <strong>{person.support_template_samples}</strong>
          </div>
          <div className="detail-card">
            <span className="stat-label">Weak Templates</span>
            <strong>{person.weak_template_samples}</strong>
          </div>
        </aside>
      </section>

      <section className="section-block">
        <div className="section-header">
          <div>
            <p className="eyebrow">Review More Photos</p>
            <h2>待确认更多照片</h2>
          </div>
        </div>
        {reviewCandidates.length === 0 ? (
          <div className="empty-state">
            <h3>当前没有待确认候选</h3>
            <p>人物样本已经比较稳定，或者还需要先积累更多正负样本。</p>
          </div>
        ) : (
          <div className="face-review-grid">
            {reviewCandidates.map((candidate) => (
              <ReviewCandidateCard key={`${candidate.face.id}-${candidate.face.logical_asset_id}`} personId={person.id} candidate={candidate} />
            ))}
          </div>
        )}
      </section>

      <section className="section-block">
        <div className="section-header">
          <div>
            <p className="eyebrow">Face Review</p>
            <h2>逐脸纠错</h2>
          </div>
        </div>
        <div className="face-review-grid">
          {person.faces.map((face) => (
            <FaceReviewCard key={face.id} face={face} people={people} />
          ))}
        </div>
      </section>

      <section className="section-block">
        <div className="section-header">
          <div>
            <p className="eyebrow">Assets</p>
            <h2>相关照片</h2>
          </div>
        </div>
        <div className="asset-grid">
          {person.assets.map((asset) => (
            <AssetCard key={asset.id} asset={asset} />
          ))}
        </div>
      </section>
    </main>
  );
}
