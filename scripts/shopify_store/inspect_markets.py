import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect_markets_and_themes():
    res = graphql_query("""
    {
      markets(first: 5) {
        edges {
          node {
            id
            name
            handle
            primary
            enabled
          }
        }
      }
      themes(first: 5) {
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
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    inspect_markets_and_themes()
