import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect_section_groups():
    q = """
    {
      translatableResources(first: 10, resourceType: ONLINE_STORE_THEME_SECTION_GROUP) {
        edges {
          node {
            resourceId
            translatableContent {
              key
              value
              digest
            }
          }
        }
      }
    }
    """
    res = graphql_query(q)
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    inspect_section_groups()
