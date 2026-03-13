import Link from "next/link";

import { ReviewCandidateCard } from "@/components/review-candidate-card";
import { getReviewInbox } from "@/lib/api";

export default async function ReviewInboxPage() {
  const inbox = await getReviewInbox().catch(() => []);
  const peopleCovered = new Set(inbox.map((item) => item.target_person_id)).size;
  const highConfidenceCount = inbox.filter((item) => item.auto_assign_eligible).length;

  return (
    <main className="page-shell people-shell">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Active Learning</p>
          <h1>Review Inbox</h1>
          <p className="hero-copy">
            这里集中展示系统当前最值得你确认的人脸候选。你每点一次“是这个人”或“不是这个人”，都会直接进入正负样本库，
            后续自动归人和待确认排序都会立刻参考这些 ground truth。
          </p>
        </div>
        <div className="hero-stats">
          <div>
            <span className="stat-label">Open Reviews</span>
            <strong>{inbox.length}</strong>
          </div>
          <div>
            <span className="stat-label">People Covered</span>
            <strong>{peopleCovered}</strong>
          </div>
          <div>
            <span className="stat-label">High Confidence</span>
            <strong>{highConfidenceCount}</strong>
          </div>
          <Link href="/people" className="hero-action-link">
            Back to People
          </Link>
        </div>
      </section>

      <section className="section-block">
        <div className="section-header">
          <div>
            <p className="eyebrow">Inbox</p>
            <h2>全局待确认收件箱</h2>
          </div>
          <Link href="/people" className="pill-link">
            查看人物库
          </Link>
        </div>
        {inbox.length === 0 ? (
          <div className="empty-state">
            <h3>当前没有待确认任务</h3>
            <p>这意味着现有样本已经比较稳定，或者你还需要先做一次人物检测与命名。</p>
          </div>
        ) : (
          <div className="face-review-grid">
            {inbox.map((candidate) => (
              <ReviewCandidateCard
                key={`${candidate.target_person_id}-${candidate.face.id}`}
                personId={candidate.target_person_id}
                candidate={candidate}
                targetPerson={{
                  id: candidate.target_person_id,
                  name: candidate.target_person_name,
                }}
              />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
