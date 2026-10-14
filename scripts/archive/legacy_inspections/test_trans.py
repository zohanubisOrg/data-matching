import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def find_translatable_links():
    q = """
    {
      translatableResources(first: 20, resourceType: LINK) {
        edges {
          node {
            resourceId
            translatableContent {
              key
              value
              digest
              locale
            }
          }
        }
      }
    }
    """
    res = graphql_query(q)
    print("LINK translatable resources:")
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    find_translatable_links()
