import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def inspect_market_languages():
    res = graphql_query("""
    {
      market(id: "gid://shopify/Market/98935341441") {
        id
        name
        webPresence {
          rootUrls {
            locale
            url
          }
        }
      }
    }
    """)
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    inspect_market_languages()
