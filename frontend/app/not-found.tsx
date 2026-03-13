import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page-shell">
      <section className="empty-state">
        <h1>Asset not found</h1>
        <p>这个逻辑照片不存在，或者后端尚未完成扫描。</p>
        <Link href="/" className="back-link">
          Back to grid
        </Link>
      </section>
    </main>
  );
}
