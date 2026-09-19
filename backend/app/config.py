"""All env-driven settings (see docs/ARCHITECTURE.md section 7)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    kafka_bootstrap: str = "localhost:19092"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "CHANGE_ME"
    topology_path: Path = ROOT / "scenarios" / "topology.yaml"
    sim_speed_default: float = 10
    sim_warmup_speed: float = 200
    run_worker_in_api: bool = True
    # M4 starts in deterministic template mode. Provider adapters can be enabled
    # explicitly once a model and key are configured.
    llm_provider: str = "template"
    llm_model: str = "CHANGE_ME"
    llm_cache_mode: str = "off"
    llm_cache_dir: Path = ROOT / "data" / "llm-cache"
    auto_investigate: bool = True
    agent_max_steps: int = 12


def get_settings() -> Settings:
    return Settings()
