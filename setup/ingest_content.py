"""
Massi-Bot — Content Catalog Ingestion Helper

Registers content from Fanvue/OnlyFans vault folders into the
content_catalog Supabase table so the chatbot engine can send PPV.

Usage (called by Claude Code during setup):
    python3 setup/ingest_content.py --platform fanvue --session 1 --tier 1 \
        --media-uuids "uuid1,uuid2,uuid3" --media-type mixed \
        --model-id "your-model-uuid"

    python3 setup/ingest_content.py --platform fanvue --session 0 --tier 0 \
        --media-uuids "uuid1,uuid2,..." --media-type image \
        --model-id "your-model-uuid"
        (session 0 + tier 0 = continuation content)

    python3 setup/ingest_content.py --list --model-id "your-model-uuid"
        (show current catalog)
"""

import argparse
import json
import os
import sys
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from persistence.supabase_client import get_client

# Tier prices in cents (must match engine/onboarding.py TIER_CONFIG)
TIER_PRICES_CENTS = {
    0: 2000,    # continuation ($20.00)
    1: 2738,    # $27.38
    2: 3656,    # $36.56
    3: 7735,    # $77.35
    4: 9246,    # $92.46
    5: 12745,   # $127.45
    6: 20000,   # $200.00
}

TIER_NAMES = {
    0: "Continuation",
    1: "Body Tease",
    2: "Top Tease",
    3: "Topless",
    4: "Bottoms Off",
    5: "Self-Play",
    6: "Climax",
}


def register_bundle(
    model_id: str,
    session_number: int,
    tier: int,
    media_uuids: list[str],
    media_type: str = "mixed",
    platform: str = "fanvue",
    source: str = "live",
) -> str:
    """Register a content bundle in the catalog. Returns bundle_id."""
    bundle_id = str(uuid.uuid4())[:8]
    price_cents = TIER_PRICES_CENTS.get(tier, 2738)

    sb = get_client()

    for i, media_uuid in enumerate(media_uuids):
        row = {
            "model_id": model_id,
            "session_number": session_number,
            "tier": tier,
            "bundle_id": bundle_id,
            "media_type": media_type,
            "price_cents": price_cents,
            "source": source,
        }

        if platform == "fanvue":
            row["fanvue_media_uuid"] = media_uuid
        else:
            row["of_media_id"] = media_uuid

        sb.table("content_catalog").insert(row).execute()

    return bundle_id


def list_catalog(model_id: str) -> None:
    """Print current content catalog for a model."""
    sb = get_client()
    resp = sb.table("content_catalog") \
        .select("session_number, tier, bundle_id, media_type, price_cents, fanvue_media_uuid, of_media_id, source") \
        .eq("model_id", model_id) \
        .order("session_number") \
        .order("tier") \
        .execute()

    rows = resp.data or []
    if not rows:
        print(f"No content found for model {model_id}")
        return

    print(f"\nContent Catalog for model {model_id}")
    print(f"{'Session':>8} {'Tier':>5} {'Name':<16} {'Price':>8} {'Bundle':<10} {'Type':<6} {'Platform IDs'}")
    print("-" * 90)

    for r in rows:
        tier = r.get("tier", 0)
        name = TIER_NAMES.get(tier, "?")
        price = f"${r.get('price_cents', 0) / 100:.2f}"
        fv = r.get("fanvue_media_uuid") or ""
        of = r.get("of_media_id") or ""
        platform_ids = f"FV:{fv[:8]}..." if fv else ""
        if of:
            platform_ids += f" OF:{of[:8]}..."

        print(f"{r.get('session_number', 0):>8} {tier:>5} {name:<16} {price:>8} {r.get('bundle_id', ''):<10} {r.get('media_type', ''):<6} {platform_ids}")

    print(f"\nTotal: {len(rows)} items")

    # Readiness check
    tiers_found = set()
    for r in rows:
        t = r.get("tier", 0)
        if t > 0:
            tiers_found.add(t)

    missing = [t for t in range(1, 7) if t not in tiers_found]
    if missing:
        print(f"\nMissing tiers: {', '.join(str(t) for t in missing)}")
        print("The selling pipeline needs at least tiers 1-4 to function.")
    else:
        print("\nAll 6 tiers present. System ready for full selling pipeline.")


def main():
    parser = argparse.ArgumentParser(description="Massi-Bot Content Catalog Ingestion")
    parser.add_argument("--model-id", required=True, help="Model UUID from Supabase models table")
    parser.add_argument("--list", action="store_true", help="List current catalog")
    parser.add_argument("--platform", choices=["fanvue", "onlyfans"], default="fanvue")
    parser.add_argument("--session", type=int, help="Session number (1-12, or 0 for continuation)")
    parser.add_argument("--tier", type=int, help="Tier (0-6, 0=continuation)")
    parser.add_argument("--media-uuids", help="Comma-separated media UUIDs from platform")
    parser.add_argument("--media-type", choices=["image", "video", "mixed"], default="mixed")
    parser.add_argument("--source", choices=["live", "ai_generated"], default="live")

    args = parser.parse_args()

    if args.list:
        list_catalog(args.model_id)
        return

    if args.session is None or args.tier is None or not args.media_uuids:
        parser.error("--session, --tier, and --media-uuids are required for registration")

    uuids = [u.strip() for u in args.media_uuids.split(",") if u.strip()]
    if not uuids:
        parser.error("No valid media UUIDs provided")

    bundle_id = register_bundle(
        model_id=args.model_id,
        session_number=args.session,
        tier=args.tier,
        media_uuids=uuids,
        media_type=args.media_type,
        platform=args.platform,
        source=args.source,
    )

    tier_name = TIER_NAMES.get(args.tier, "?")
    price = TIER_PRICES_CENTS.get(args.tier, 0) / 100

    print(f"Registered bundle {bundle_id}:")
    print(f"  Session: {args.session}")
    print(f"  Tier: {args.tier} ({tier_name}) — ${price:.2f}")
    print(f"  Media items: {len(uuids)}")
    print(f"  Platform: {args.platform}")
    print(f"  Source: {args.source}")


if __name__ == "__main__":
    main()
