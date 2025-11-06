from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
import logging

from models import Base


# Configuration
DATABASE_DIR = Path(__file__).parent / "traffic_fines"
DATABASE_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATABASE_DIR}/fines.db"

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """
    Database configuration with connection pooling strategy
    
    Architectural Considerations:
    - SQLite with StaticPool for thread-safe operations
    - Check same thread disabled for FastAPI async context
    - WAL mode for concurrent read performance
    """
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        
        # Engine configuration for optimal SQLite performance
        self.engine = create_engine(
            database_url,
            connect_args={
                "check_same_thread": False,  # FastAPI async compatibility
                "timeout": 30,  # Connection timeout
            },
            poolclass=StaticPool,  # Single connection pool for SQLite
            echo=False,  # Set True for SQL query logging
        )
        
        # Session factory with autocommit/autoflush disabled for explicit control
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        self._initialize_database()
    
    def _initialize_database(self):
        """Create tables and configure SQLite optimizations"""
        try:
            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            
            # Enable WAL mode for better concurrent access
            with self.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
                conn.execute(text("PRAGMA temp_store=MEMORY"))
                conn.commit()
            
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions
        
        Ensures proper session lifecycle management:
        - Automatic commit on success
        - Rollback on exception
        - Session cleanup
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

# Global database instance
db_config = DatabaseConfig()

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions
    
    Usage in endpoints:
        @app.get("/fines")
        def list_fines(db: Session = Depends(get_db)):
            ...
    """
    with db_config.get_session() as session:
        yield session
