import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect():
    # 1. Check shop locales
    res_locales = graphql_query("""
    {
      shopLocales {
        locale
        name
        primary
        published
      }
    }
    """)
    print("=== SHOP LOCALES ===")
    print(json.dumps(res_locales, indent=2))

    # 2. Check translatable resource types
    res_enum = graphql_query("""
    {
      __type(name: "TranslatableResourceType") {
        enumValues {
          name
        }
      }
    }
    """)
    enums = [x["name"] for x in res_enum.get("data", {}).get("__type", {}).get("enumValues", [])]
    print("\n=== TRANSLATABLE RESOURCE TYPES ===")
    print(enums)

    # 3. Check menu resource translations
    # Find Menu resource
    menus = graphql_query("""
    {
      menus(first: 5) {
        edges {
          node {
            id
            handle
            title
            items {
              id
              title
              items {
                id
                title
              }
            }
          }
        }
      }
    }
    """)
    print("\n=== MENUS ===")
    print(json.dumps(menus, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    inspect()
