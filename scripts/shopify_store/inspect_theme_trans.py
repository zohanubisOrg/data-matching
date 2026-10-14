import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect_theme_translations():
    # 1. Get Main theme ID
    theme_res = graphql_query("""
    {
      themes(first: 5, roles: [MAIN]) {
        edges {
          node {
            id
            name
            role
          }
        }
      }
    }
    """)
    main_theme = theme_res["data"]["themes"]["edges"][0]["node"]
    print("Main Theme:", main_theme)

    # 2. Check translatable resources for ONLINE_STORE_THEME
    q = f"""
    {{
      translatableResources(first: 10, resourceType: ONLINE_STORE_THEME) {{
        edges {{
          node {{
            resourceId
            translatableContent {{
              key
              value
              digest
              locale
            }}
          }}
        }}
      }}
    }}
    """
    res = graphql_query(q)
    print("Theme translatable resources count:", len(res.get("data", {}).get("translatableResources", {}).get("edges", [])))
    if res.get("data", {}).get("translatableResources", {}).get("edges"):
        first_node = res["data"]["translatableResources"]["edges"][0]["node"]
        print("First node resourceId:", first_node["resourceId"])
        print("First node translatableContent sample (first 5):")
        print(json.dumps(first_node["translatableContent"][:5], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    inspect_theme_translations()
