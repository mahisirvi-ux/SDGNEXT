from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS technical_documents (
                id SERIAL PRIMARY KEY,
                touchpoint_id INTEGER REFERENCES integration_touchpoints(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                file_data TEXT NOT NULL,
                file_type VARCHAR(50) DEFAULT 'docx',
                received_from VARCHAR(150),
                received_at TIMESTAMP DEFAULT NOW(),
                notes TEXT
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_technical_documents_touchpoint_id ON technical_documents(touchpoint_id)"))
        conn.commit()
        print("Migration complete: technical_documents table ready.")
    except Exception as e:
        print(f"Error: {e}")
