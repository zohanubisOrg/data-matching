import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect_theme_sections_trans():
    types_to_check = [
        "ONLINE_STORE_THEME_SETTINGS_DATA_SECTIONS",
        "ONLINE_STORE_THEME_JSON_TEMPLATE",
        "ONLINE_STORE_THEME_LOCALE_CONTENT",
        "PAGE",
        "COLLECTION"
    ]
    for rtype in types_to_check:
        q = f"""
        {{
          translatableResources(first: 5, resourceType: {rtype}) {{
            edges {{
              node {{
                resourceId
                translatableContent {{
                  key
                  value
                  digest
                }}
              }}
            }}
          }}
        }}
        """
        res = graphql_query(q)
        edges = res.get("data", {}).get("translatableResources", {}).get("edges", [])
        print(f"=== {rtype}: found {len(edges)} ===")
        for e in edges:
            node = e["node"]
            print(f"  ID: {node['resourceId']}")
            for tc in node.get("translatableContent", [])[:3]:
                print(f"    - {tc['key']}: {tc['value'][:50] if tc['value'] else ''}")

if __name__ == "__main__":
    inspect_theme_sections_trans()
