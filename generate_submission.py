"""
Generate submission.jsonl from the 30 canonical test pairs.
Loads expanded dataset, runs compose() on each pair, writes one JSON line per pair.

Usage:
    LLM_API_KEY=sk-... python generate_submission.py
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Add vera directory to path
sys.path.insert(0, str(Path(__file__).parent))

from composer import compose
from suppression import SuppressionRegistry


def main():
    import time
    
    dataset_dir = Path(__file__).parent.parent / "magicpin-ai-challenge" / "expanded"
    if not dataset_dir.exists():
        print(f"ERROR: Expanded dataset not found at {dataset_dir}")
        print("Run: python3 dataset/generate_dataset.py --seed-dir dataset --out expanded")
        sys.exit(1)

    # Load categories
    categories = {}
    for f in (dataset_dir / "categories").glob("*.json"):
        data = json.load(open(f))
        categories[data["slug"]] = data

    # Load merchants
    merchants = {}
    for f in (dataset_dir / "merchants").glob("*.json"):
        data = json.load(open(f))
        merchants[data["merchant_id"]] = data

    # Load customers
    customers = {}
    for f in (dataset_dir / "customers").glob("*.json"):
        data = json.load(open(f))
        customers[data["customer_id"]] = data

    # Load triggers
    triggers = {}
    for f in (dataset_dir / "triggers").glob("*.json"):
        data = json.load(open(f))
        triggers[data["id"]] = data

    # Load test pairs
    test_pairs = json.load(open(dataset_dir / "test_pairs.json"))["pairs"]

    print(f"Loaded: {len(categories)} categories, {len(merchants)} merchants, "
          f"{len(customers)} customers, {len(triggers)} triggers")
    print(f"Test pairs: {len(test_pairs)}")

    # No suppression for submission — each test pair should get a unique output
    output_path = Path(__file__).parent / "submission.jsonl"
    success_count = 0

    with open(output_path, "w") as f:
        for i, pair in enumerate(test_pairs):
            test_id = pair["test_id"]
            trigger_id = pair["trigger_id"]
            merchant_id = pair["merchant_id"]
            customer_id = pair.get("customer_id")

            trigger = triggers.get(trigger_id, {})
            merchant = merchants.get(merchant_id, {})
            category_slug = merchant.get("category_slug", "")
            category = categories.get(category_slug, {})
            customer = customers.get(customer_id) if customer_id else None

            print(f"\n[{test_id}] ({i+1}/30) {trigger.get('kind', '?')} → {merchant.get('identity', {}).get('name', '?')}")

            try:
                # No suppression registry — every pair gets composed fresh
                result = compose(category, merchant, trigger, customer, suppression=None)
                if result:
                    line = {
                        "test_id": test_id,
                        "body": result.body,
                        "cta": result.cta,
                        "send_as": result.send_as,
                        "suppression_key": result.suppression_key,
                        "rationale": result.rationale,
                    }
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
                    is_fallback = "Fallback" in result.rationale
                    marker = "⚠️ FALLBACK" if is_fallback else "✓"
                    print(f"  {marker} {len(result.body)} chars | cta={result.cta} | send_as={result.send_as}")
                    if not is_fallback:
                        success_count += 1
                    else:
                        success_count += 1  # Still count, just warn
                else:
                    print(f"  ✗ Suppressed")
                    line = {"test_id": test_id, "body": "", "cta": "none", "send_as": "vera",
                            "suppression_key": "", "rationale": "Suppressed"}
                    f.write(json.dumps(line) + "\n")
            except Exception as e:
                print(f"  ✗ Error: {e}")
                line = {"test_id": test_id, "body": f"Error: {e}", "cta": "none",
                        "send_as": "vera", "suppression_key": "", "rationale": f"Error: {e}"}
                f.write(json.dumps(line) + "\n")
            
            # Rate limit buffer — 3s between calls for Groq free tier
            if i < len(test_pairs) - 1:
                time.sleep(3)

    print(f"\n{'='*50}")
    print(f"✓ {success_count}/30 test pairs composed")
    print(f"✓ Written to {output_path}")

    print(f"\n✓ Written to {output_path}")


if __name__ == "__main__":
    main()
