import sys
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def verify():
    q = """
    {
      translatableResources(first: 60, resourceType: LINK) {
        edges {
          node {
            resourceId
            translatableContent {
              key
              value
            }
            da: translations(locale: "da") {
              key
              value
            }
            vi: translations(locale: "vi") {
              key
              value
            }
          }
        }
      }
    }
    """
    res = graphql_query(q)
    edges = res.get("data", {}).get("translatableResources", {}).get("edges", [])
    targets = ['Batter & Breading', 'Asian Baking Mixes', 'Flour & Starch', 'Tapioca Products', 'Rice, Flour & Dry Goods']
    print("\n--- TARGET VERIFICATION FOR USER'S SCREENSHOT ITEMS ---")
    for e in edges:
        node = e["node"]
        orig = node.get("translatableContent", [{}])[0].get("value")
        if orig in targets:
            da_val = node.get("da", [{}])[0].get("value") if node.get("da") else "(none)"
            vi_val = node.get("vi", [{}])[0].get("value") if node.get("vi") else "(none)"
            print(f"  🎯 [{orig}] => DA: '{da_val}' | VI: '{vi_val}'")

if __name__ == "__main__":
    verify()
