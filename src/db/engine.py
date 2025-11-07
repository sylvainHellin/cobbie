from sqlmodel import create_engine

from src.config import DB_PATH

# Create engines with connection pooling and better connection management
ENGINE = create_engine(
    url=f"sqlite:///{DB_PATH}",
    # echo=True,
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections every hour
    connect_args={
        "timeout": 30,  # Connection timeout
        "check_same_thread": False,
    },
)
