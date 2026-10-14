import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def list_all_collections():
    res = graphql_query("""
    {
      collections(first: 20) {
        edges {
          node {
            id
            title
            handle
          }
        }
      }
    }
    """)
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    list_all_collections()
