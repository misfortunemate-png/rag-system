import yaml, sys
from pathlib import Path
from datetime import date

path = Path("data/auth_tokens.yaml")
if not path.exists():
    sys.exit(0)
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
today = date.today()
for e in data.get("tokens", []):
    tid = e.get("id", "?")
    exp = e.get("expires")
    if exp and date.fromisoformat(str(exp)) < today:
        status = "[expired]"
    else:
        status = "[active] "
    print(f"  {status} {tid}")
