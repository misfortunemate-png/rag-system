"""Agent configuration: dataclass, persistence, presets."""
from dataclasses import dataclass, asdict
import json
from pathlib import Path

APP_VERSION = "0.3.0"

PRESETS = [
    "deepseek/deepseek-v4-flash",
    "google/gemini-2.5-flash",
    "anthropic/claude-haiku-4-5",
]
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
SETTINGS_PATH = Path("settings.json")

ANSWER_STYLES = {
    "brief": "結論のみ",
    "standard": "標準",
    "detailed": "詳細",
}

# Approximate cost per 1M tokens (USD) — rough estimates only
COST_PER_1M: dict = {
    "deepseek/deepseek-v4-flash": {"input": 0.07, "output": 0.28},
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "anthropic/claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}


@dataclass
class AgentConfig:
    planner_enabled: bool = False
    planner_model: str = DEFAULT_MODEL
    loop_model: str = DEFAULT_MODEL
    composer_model: str = DEFAULT_MODEL
    max_loops: int = 15
    top_k: int = 3
    answer_style: str = "standard"  # "brief" | "standard" | "detailed"


def load_config() -> AgentConfig:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            valid = set(AgentConfig.__dataclass_fields__.keys())
            return AgentConfig(**{k: v for k, v in data.items() if k in valid})
        except Exception:
            pass
    return AgentConfig()


def save_config(config: AgentConfig) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    rates = COST_PER_1M.get(model)
    if not rates:
        return None
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
