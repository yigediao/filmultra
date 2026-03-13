from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import engine


def run_startup_migrations() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "faces" in tables:
        columns = {column["name"] for column in inspector.get_columns("faces")}
        if "assignment_locked" not in columns:
            statements.append("ALTER TABLE faces ADD COLUMN assignment_locked BOOLEAN NOT NULL DEFAULT 0")
        if "is_excluded" not in columns:
            statements.append("ALTER TABLE faces ADD COLUMN is_excluded BOOLEAN NOT NULL DEFAULT 0")

    if "logical_assets" in tables:
        columns = {column["name"] for column in inspector.get_columns("logical_assets")}
        if "face_scan_status" not in columns:
            statements.append("ALTER TABLE logical_assets ADD COLUMN face_scan_status VARCHAR(32) NULL")
        if "face_scan_signature" not in columns:
            statements.append("ALTER TABLE logical_assets ADD COLUMN face_scan_signature VARCHAR(1024) NULL")
        if "face_scan_completed_at" not in columns:
            statements.append("ALTER TABLE logical_assets ADD COLUMN face_scan_completed_at DATETIME NULL")
        if "face_scan_status" not in columns:
            statements.append("CREATE INDEX ix_logical_assets_face_scan_status ON logical_assets (face_scan_status)")

    if "face_review_feedback" not in tables:
        statements.extend(
            [
                """
                CREATE TABLE face_review_feedback (
                    id INTEGER NOT NULL PRIMARY KEY,
                    person_id INTEGER NOT NULL,
                    logical_asset_id INTEGER NOT NULL,
                    source_face_id INTEGER NULL,
                    decision VARCHAR(16) NOT NULL,
                    suggested_score FLOAT NULL,
                    embedding_digest VARCHAR(64) NOT NULL,
                    review_count INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(person_id) REFERENCES people (id)
                )
                """,
                "CREATE INDEX ix_face_review_feedback_person_id ON face_review_feedback (person_id)",
                "CREATE INDEX ix_face_review_feedback_logical_asset_id ON face_review_feedback (logical_asset_id)",
                "CREATE INDEX ix_face_review_feedback_source_face_id ON face_review_feedback (source_face_id)",
                "CREATE INDEX ix_face_review_feedback_decision ON face_review_feedback (decision)",
                "CREATE INDEX ix_face_review_feedback_embedding_digest ON face_review_feedback (embedding_digest)",
                """
                CREATE UNIQUE INDEX uq_face_review_feedback_person_asset_digest
                ON face_review_feedback (person_id, logical_asset_id, embedding_digest)
                """,
            ]
        )

    if "logical_assets" in tables:
        statements.append(
            """
            UPDATE logical_assets
            SET face_scan_status = COALESCE(face_scan_status, 'completed'),
                face_scan_completed_at = COALESCE(face_scan_completed_at, updated_at, created_at)
            WHERE id IN (SELECT DISTINCT logical_asset_id FROM faces)
            """
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
