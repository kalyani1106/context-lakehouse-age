import os
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

class Settings(BaseModel):
    # App
    APP_NAME: str = "Context Lakehouse & Knowledge Graph Pipeline"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=True)
    
    # PostgreSQL & Apache AGE
    POSTGRES_HOST: str = Field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    POSTGRES_PORT: int = Field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5455")))
    POSTGRES_DB: str = Field(default_factory=lambda: os.getenv("POSTGRES_DB", "postgres"))
    POSTGRES_USER: str = Field(default_factory=lambda: os.getenv("POSTGRES_USER", "postgres"))
    POSTGRES_PASSWORD: str = Field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "postgres"))
    AGE_GRAPH_NAME: str = Field(default_factory=lambda: os.getenv("AGE_GRAPH_NAME", "knowledge_graph"))
    
    # Lakehouse Storage
    LAKEHOUSE_ROOT: Path = Field(default_factory=lambda: Path(os.getenv("LAKEHOUSE_ROOT", str(Path(__file__).resolve().parent / "lakehouse_storage"))).resolve())
    
    # Text Extraction & Chunking
    CHUNK_SIZE: int = Field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "800")))
    CHUNK_OVERLAP: int = Field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "150")))
    
    # LLM Settings (OpenAI / Gemini / Local / Fallback)
    LLM_PROVIDER: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "auto")) # auto, openai, gemini, heuristic
    OPENAI_API_KEY: str | None = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    OPENAI_MODEL: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    GEMINI_API_KEY: str | None = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    GEMINI_MODEL: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))

    @property
    def postgres_dsn(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
