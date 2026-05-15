from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Update with your actual PostgreSQL credentials
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:Praj%40123@localhost:5432/sdgnext"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()