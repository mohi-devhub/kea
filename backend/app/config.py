"""All env-driven settings (see docs/ARCHITECTURE.md section 7)."""

from pathlib import Path

from pydantic import SecretStr, field_validator
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
    # Deterministic template mode is the default; a real provider needs a name, a model and a key.
    llm_provider: str = "template"  # template | openai | anthropic | sarvam
    llm_model: str = "CHANGE_ME"
    # Optional per-role overrides (empty = use the global provider and model).
    agent_llm_provider: str = ""
    agent_llm_model: str = ""
    baseline_llm_provider: str = ""
    baseline_llm_model: str = ""
    fix_llm_provider: str = ""
    fix_llm_model: str = ""
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    sarvam_api_key: SecretStr | None = None
    llm_reasoning_effort: str = "low"
    llm_max_output_tokens: int = 4000
    llm_timeout_s: float = 60.0
    llm_cache_mode: str = "off"  # off | record | replay
    llm_cache_dir: Path = ROOT / ".llm-cache"
    # Fix flow (propose-only): backend is codex_cli with a fallback to llm_tool_loop.
    fix_backend: str = "codex_cli"  # codex_cli | llm_tool_loop
    fix_cache_mode: str = "off"  # off | record | replay
    fix_cache_dir: Path = ROOT / ".llm-cache" / "fix"
    demo_repo_path: Path = ROOT / ".demo-repos" / "payment-service"
    sandbox_dir: Path = ROOT / ".sandboxes"
    auto_investigate: bool = True
    agent_max_steps: int = 12

    @field_validator("llm_cache_dir", "fix_cache_dir", "demo_repo_path", "sandbox_dir")
    @classmethod
    def _cache_dir_from_repo_root(cls, value: Path) -> Path:
        """A relative path in .env means relative to the repo, not to whatever cwd started us."""
        return value if value.is_absolute() else ROOT / value

    def secret_values(self) -> list[str]:
        """Every configured secret, so outbound checks can refuse to send any of them."""
        keys = (self.openai_api_key, self.anthropic_api_key, self.sarvam_api_key)
        return [k.get_secret_value() for k in keys if k is not None and k.get_secret_value()]


def get_settings() -> Settings:
    return Settings()
