"""Agent configuration: dataclass, persistence, presets."""
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path

DOCUMENTS_YAML = Path("documents.yaml")


def load_documents_yaml() -> list[dict]:
    import yaml
    if not DOCUMENTS_YAML.exists():
        return []
    with open(DOCUMENTS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f).get("documents", [])

APP_VERSION = "0.5.0"

# chat-pwa 準拠のモデルプリセット（M4）
PRESETS = [
    # --- OpenRouter ---
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
    "google/gemini-2.5-flash",
    "google/gemini-3.6-flash",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-opus-4.6",
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-luna",
    "qwen/qwen3.7-plus",
    "minimax/minimax-m3",
    # --- Anthropic direct ---
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
SETTINGS_PATH = Path("settings.json")

ANSWER_STYLES = {
    "brief": "結論のみ",
    "standard": "標準",
    "detailed": "詳細",
}

# Approximate cost per 1M tokens (USD)
COST_PER_1M: dict = {
    "deepseek/deepseek-v4-flash": {"input": 0.07, "output": 0.28},
    "deepseek/deepseek-v4-pro": {"input": 0.14, "output": 0.55},
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "google/gemini-3.6-flash": {"input": 0.10, "output": 0.40},
    "anthropic/claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "anthropic/claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "anthropic/claude-opus-4.6": {"input": 15.00, "output": 75.00},
    "openai/gpt-5.6-sol": {"input": 5.00, "output": 15.00},
    "openai/gpt-5.6-luna": {"input": 2.00, "output": 8.00},
    "qwen/qwen3.7-plus": {"input": 0.50, "output": 1.50},
    "minimax/minimax-m3": {"input": 0.40, "output": 1.60},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
}


@dataclass
class AgentConfig:
    planner_enabled: bool = False
    planner_model: str = DEFAULT_MODEL
    loop_model: str = DEFAULT_MODEL
    composer_model: str = DEFAULT_MODEL
    max_loops: int = 15
    top_k: int = 5
    answer_style: str = "standard"
    # M4: アドバイザー
    advisor_model: str = DEFAULT_MODEL
    advisor_trigger_always: bool = False
    advisor_trigger_planner: bool = False
    advisor_trigger_stall: bool = True
    advisor_trigger_unresolved: bool = False
    advisor_k: int = 2        # 難航検知: 連続空振りループ数
    early_stop_k: int = 3     # 早期打ち切り: 連続空振りループ数
    # M4.5: 文書スコープ（None = 全文書対象、[] = 全除外）
    selected_doc_ids: list | None = None
    # M5b: domain検索フィルタ（None = 全domain対象）
    selected_domains: list | None = None
    # M6-1: Web照合
    web_search_enabled: bool = True
    web_search_backend: str = "duckduckgo"


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
