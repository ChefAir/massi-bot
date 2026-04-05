"""
Massi-Bot — Re-embed All Memories with New Embedding Model

Run this after migrating from MiniLM (384-dim) to BGE-M3 (1024-dim).
Reads every row from subscriber_memory and persona_memory,
re-encodes with the current embedding model, and updates the row.

Usage:
    python3 setup/reembed_memories.py
    python3 setup/reembed_memories.py --dry-run   (shows count without updating)
    python3 setup/reembed_memories.py --batch 50   (batch size, default 100)
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from persistence.supabase_client import get_client
from llm.memory_store import _get_encoder


def reembed_table(table_name: str, batch_size: int = 100, dry_run: bool = False) -> int:
    """Re-embed all rows in a table. Returns number of rows updated."""
    sb = get_client()
    encoder = _get_encoder()
    if not encoder:
        print("ERROR: Embedding model not available.")
        return 0

    # Count total rows
    count_resp = sb.table(table_name).select("id", count="exact").execute()
    total = count_resp.count or 0
    print(f"\n{table_name}: {total} rows to re-embed")

    if dry_run:
        return total

    # Process in batches
    updated = 0
    offset = 0

    while offset < total:
        resp = sb.table(table_name) \
            .select("id, fact") \
            .range(offset, offset + batch_size - 1) \
            .execute()

        rows = resp.data or []
        if not rows:
            break

        # Batch encode all facts
        facts = [r.get("fact", "") for r in rows]
        embeddings = encoder.encode(facts, normalize_embeddings=True, show_progress_bar=False)

        # Update each row
        for row, emb in zip(rows, embeddings):
            try:
                sb.table(table_name).update({
                    "embedding": emb.tolist()
                }).eq("id", row["id"]).execute()
                updated += 1
            except Exception as e:
                print(f"  ERROR updating {row['id']}: {e}")

        offset += batch_size
        print(f"  {updated}/{total} rows updated...")

    print(f"  Done: {updated}/{total} rows re-embedded in {table_name}")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Re-embed all memories with new model")
    parser.add_argument("--dry-run", action="store_true", help="Count rows without updating")
    parser.add_argument("--batch", type=int, default=100, help="Batch size (default: 100)")
    args = parser.parse_args()

    print(f"Embedding model: {os.environ.get('EMBEDDING_MODEL', 'BAAI/bge-m3')}")

    if args.dry_run:
        print("DRY RUN — counting rows only\n")

    start = time.time()
    total = 0
    total += reembed_table("subscriber_memory", batch_size=args.batch, dry_run=args.dry_run)
    total += reembed_table("persona_memory", batch_size=args.batch, dry_run=args.dry_run)

    elapsed = time.time() - start
    action = "counted" if args.dry_run else "re-embedded"
    print(f"\n{'='*50}")
    print(f"Total: {total} rows {action} in {elapsed:.1f}s")

    if not args.dry_run:
        print("\nDone! Your memories are now using the new embedding model.")
        print("Restart Docker containers to pick up the changes: docker compose restart")


if __name__ == "__main__":
    main()
