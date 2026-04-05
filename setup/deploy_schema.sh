#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Massi-Bot — Deploy Database Schema to Supabase
# ═══════════════════════════════════════════════════════════════
#
# This script concatenates all migration files in the correct order
# and outputs the combined SQL. You can either:
#
#   A) Copy-paste the output into the Supabase SQL Editor
#      (Dashboard → SQL Editor → New Query → Paste → Run)
#
#   B) Pipe to a file:
#      bash setup/deploy_schema.sh > combined_schema.sql
#
# Migration order matters — each file builds on the previous ones.
# ═══════════════════════════════════════════════════════════════

set -e

MIGRATIONS_DIR="$(dirname "$0")/../migrations"

# Ordered list of migrations
MIGRATIONS=(
    "000_full_schema.sql"
    "deploy_pgvector_memory.sql"
    "deploy_persona_memory.sql"
    "001_model_profile_columns.sql"
    "002_of_media_id.sql"
    "add_content_descriptions.sql"
    "003_memory_context_upgrade.sql"
    "004_system_audit_fixes.sql"
    "005_memory_cleanup_and_index.sql"
    "006_ebbinghaus_forgetting.sql"
    "007_template_rewards.sql"
    "008_bge_m3_embeddings.sql"
)

echo "-- ═══════════════════════════════════════════════════════════"
echo "-- Massi-Bot Combined Schema — Generated $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "-- Copy this entire output into the Supabase SQL Editor and run it."
echo "-- ═══════════════════════════════════════════════════════════"
echo ""

for migration in "${MIGRATIONS[@]}"; do
    filepath="$MIGRATIONS_DIR/$migration"
    if [ -f "$filepath" ]; then
        echo "-- ─────────────────────────────────────────────────────────"
        echo "-- Migration: $migration"
        echo "-- ─────────────────────────────────────────────────────────"
        echo ""
        cat "$filepath"
        echo ""
        echo ""
    else
        echo "-- WARNING: Migration file not found: $migration" >&2
    fi
done

echo "-- ═══════════════════════════════════════════════════════════"
echo "-- Schema deployment complete."
echo "-- ═══════════════════════════════════════════════════════════"
