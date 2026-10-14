import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect_theme_data_sections():
    q = """
    {
      translatableResource(resourceId: "gid://shopify/OnlineStoreThemeSettingsDataSections/189930996097") {
        resourceId
        translatableContent {
          key
          value
          digest
        }
      }
    }
    """
    res = graphql_query(q)
    tc = res.get("data", {}).get("translatableResource", {}).get("translatableContent", [])
    print(f"Total translatable items in settings data sections: {len(tc)}")
    for item in tc:
        val = item['value'][:60] if item['value'] else ''
        print(f"  {item['key']} -> '{val}' (digest: {item['digest'][:8]}...)")

if __name__ == "__main__":
    inspect_theme_data_sections()
