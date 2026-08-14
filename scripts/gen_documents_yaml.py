"""rag_file_list.json → documents.yaml 生成スクリプト"""

import json
import re
import os
import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAG_FILE_LIST = REPO / "0814scraping_plan" / "rag_file_list.json"
OUTPUT = REPO / "documents.yaml"
DATA_RAW = REPO / "data" / "raw"

DOMAIN_RULES = [
    (r"01_mlit/shiyousho/.*kenchiku", "建築"),
    (r"01_mlit/shiyousho/.*mokuzou", "建築"),
    (r"01_mlit/shiyousho/.*denki", "電気"),
    (r"01_mlit/shiyousho/.*kikai", "機械"),
    (r"01_mlit/sekkei/", "設計"),
    (r"01_mlit/sekisan/", ""),
    (r"02_denki/", "電気"),
    (r"03_shobo/", "消防"),
    (r"05_tosou/", "塗装"),
    (r"07_mhlw/", "衛生"),
    (r"08_gyoukai/", ""),
    (r"09_maker/", ""),
    (r"10_hourei/", ""),
]


def path_to_slug(path: str) -> str:
    stem = Path(path).stem
    # XML: use part before first underscore (e.g. law-89a_電気事業法 → law-89a)
    if path.endswith(".xml"):
        slug = stem.split("_")[0]
    else:
        slug = stem
    slug = slug.lower()
    slug = slug.replace("_", "-")
    # remove Japanese characters
    slug = re.sub(r"[^\x00-\x7f]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def get_domain(path: str) -> str:
    for pattern, domain in DOMAIN_RULES:
        if re.search(pattern, path):
            return domain
    return ""


def main():
    with open(RAG_FILE_LIST, encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    seen_slugs: dict[str, int] = {}

    for group in data["files"]:
        for file_entry in group.get("files", []):
            path = file_entry["path"]
            if file_entry.get("glob"):
                continue
            if path.endswith(".txt"):
                continue
            # exclude 11_scraped
            if path.startswith("11_scraped"):
                continue

            raw_path = DATA_RAW / path
            if not raw_path.exists():
                print(f"SKIP (not found): {path}")
                continue

            slug = path_to_slug(path)
            if slug in seen_slugs:
                seen_slugs[slug] += 1
                slug = f"{slug}-{seen_slugs[slug]}"
            else:
                seen_slugs[slug] = 1

            domain = get_domain(path)
            is_xml = path.endswith(".xml")

            entry = {
                "id": slug,
                "doc_slug": slug,
                "title": file_entry["title"],
                "domain": domain,
                "tags": [],
                "profile": "hourei" if is_xml else "auto",
                "file_path": f"data/raw/{path}",
                "ingest_at": "2026-08-14",
                "status": "active",
            }
            entries.append(entry)

    doc = {"documents": entries}

    class QuotedStr(str):
        pass

    def quoted_str_representer(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')

    yaml.add_representer(QuotedStr, quoted_str_representer)

    for e in entries:
        e["file_path"] = QuotedStr(e["file_path"])
        e["ingest_at"] = QuotedStr(e["ingest_at"])

    with open(OUTPUT, "w", encoding="utf-8") as f:
        yaml.dump(
            doc,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=200,
        )

    print(f"Generated {len(entries)} entries → {OUTPUT}")


if __name__ == "__main__":
    main()
