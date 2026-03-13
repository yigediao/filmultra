import Link from "next/link";

import { FaceJobsPanel } from "@/components/face-jobs-panel";
import { ClusterAssignForm } from "@/components/cluster-assign-form";
import { getClusters, getPeople, getPreviewUrl } from "@/lib/api";

export default async function PeoplePage() {
  const [people, clusters] = await Promise.all([
    getPeople().catch(() => []),
    getClusters().catch(() => []),
  ]);
  const totalPositiveSamples = people.reduce((sum, person) => sum + person.positive_training_samples, 0);

  return (
    <main className="page-shell people-shell">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Face Recognition</p>
          <h1>People</h1>
          <p className="hero-copy">
            先做自动检测与聚类，再把未命名人物簇手工命名为正式人物。你每次手工确认“是谁”和“不是谁”，系统都会把这些
            ground truth 记成训练样本，后续重聚类和新照片归人会优先参考这些样本。现在也可以直接进入全局待确认收件箱，
            集中处理系统最值得你确认的边界样本。
          </p>
        </div>
        <div className="hero-stats">
          <div>
            <span className="stat-label">Named People</span>
            <strong>{people.length}</strong>
          </div>
          <div>
            <span className="stat-label">Open Clusters</span>
            <strong>{clusters.length}</strong>
          </div>
          <div>
            <span className="stat-label">Training Samples</span>
            <strong>{totalPositiveSamples}</strong>
          </div>
          <Link href="/people/review" className="hero-action-link">
            Open Review Inbox
          </Link>
        </div>
      </section>

      <FaceJobsPanel />

      <section className="section-block">
        <div className="section-header">
          <div>
            <p className="eyebrow">Named</p>
            <h2>已命名人物</h2>
          </div>
          <Link href="/people/review" className="pill-link">
            全局待确认收件箱
          </Link>
        </div>
        {people.length === 0 ? (
          <div className="empty-state">
            <h3>还没有已命名人物</h3>
            <p>先跑一次人物识别，再把下方未命名聚类命名即可。</p>
          </div>
        ) : (
          <div className="people-grid">
            {people.map((person) => {
              const coverUrl = getPreviewUrl(person.cover_preview_url);
              return (
                <Link href={`/people/${person.id}`} key={person.id} className="person-card">
                  <div className="person-cover">
                    {coverUrl ? (
                      <img src={coverUrl} alt={person.name} />
                    ) : (
                      <div className="asset-thumb fallback">No Face</div>
                    )}
                  </div>
                  <div className="person-meta">
                    <div className="asset-topline">
                      <h3>{person.name}</h3>
                      <span>{person.face_count} faces</span>
                    </div>
                    <p>{person.asset_count} assets linked</p>
                    <p>
                      {person.positive_training_samples} positive / {person.negative_training_samples} negative samples
                    </p>
                    <p>
                      {person.core_template_samples} core / {person.support_template_samples} support / {person.weak_template_samples} weak
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      <section className="section-block">
        <div className="section-header">
          <div>
            <p className="eyebrow">Clusters</p>
            <h2>未命名聚类</h2>
          </div>
        </div>
        {clusters.length === 0 ? (
          <div className="empty-state">
            <h3>没有待命名聚类</h3>
            <p>如果还没跑识别，先点击上面的 Detect Faces。</p>
          </div>
        ) : (
          <div className="cluster-grid">
            {clusters.map((cluster) => (
              <article key={cluster.cluster_id} className="cluster-card">
                <div className="asset-topline">
                  <h3>{cluster.cluster_id}</h3>
                  <span>{cluster.face_count} faces</span>
                </div>
                <p className="muted-copy">{cluster.asset_count} assets involved</p>
                <div className="face-strip">
                  {cluster.sample_faces.map((face) => {
                    const previewUrl = getPreviewUrl(face.preview_url);
                    return previewUrl ? (
                      <img key={face.id} src={previewUrl} alt={cluster.cluster_id} className="face-thumb" />
                    ) : null;
                  })}
                </div>
                <ClusterAssignForm clusterId={cluster.cluster_id} />
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
