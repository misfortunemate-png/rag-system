"""
R1アドバイザー発動検証スクリプト
メタルモール問でアドバイザー難航検知の発動ループ番号・所要時間を計測する。
"""
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import run_pre_composer
from src.config import AgentConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

QUESTION = "屋内配線の保護としてメタルモールを使ってはならない部屋は"

config = AgentConfig(
    planner_enabled=True,
    advisor_trigger_stall=True,
    advisor_trigger_planner=False,  # isolate budget/stall trigger only
    advisor_trigger_always=False,
    advisor_k=2,
    max_loops=15,
)

print(f"=== R1 アドバイザー発動テスト ===")
print(f"質問: {QUESTION}")
print(f"設定: advisor_k={config.advisor_k}, max_loops={config.max_loops}, "
      f"search_budget={int(config.max_loops * 0.6)}")
print()

t0 = time.perf_counter()
result = run_pre_composer(QUESTION, config)
elapsed = time.perf_counter() - t0

trace = result["trace"]
advisor_loop = None
for entry in trace:
    if entry.get("advisor"):
        advisor_loop = entry["loop"]
        advisor_decision = entry.get("decision", "")
        advisor_reason = entry.get("reason", "")
        break

loop_count = len([e for e in trace if not e.get("advisor") and not e.get("early_stop")])
max_loops_hit = result.get("debug_partial", {}).get("loop", {}).get("max_loops_hit", False)
early_stop = result.get("debug_partial", {}).get("loop", {}).get("early_stop", False)
advisor_fired = result.get("advisor_state", {}).get("fired", False)

print("=== 結果 ===")
print(f"実行ループ数: {loop_count}")
print(f"アドバイザー発動: {'YES' if advisor_loop else 'NO'}")
if advisor_loop:
    print(f"  発動ループ番号: {advisor_loop}")
    print(f"  裁定: {advisor_decision}")
    print(f"  理由: {advisor_reason}")
print(f"早期打ち切り: {early_stop}")
print(f"MAX_LOOPS到達: {max_loops_hit}")
print(f"所要時間: {elapsed:.1f}s")
print()
print(f"=== 比較 ===")
print(f"修正前: 12ループ / 136.4s / アドバイザー未発動")
print(f"修正後: {loop_count}ループ / {elapsed:.1f}s / "
      f"{'ループ' + str(advisor_loop) + 'で発動' if advisor_loop else 'アドバイザー未発動'}")
