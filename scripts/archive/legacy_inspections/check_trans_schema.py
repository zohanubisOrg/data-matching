import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def check_translations_register_schema():
    res = graphql_query("""
    {
      __type(name: "TranslationInput") {
        inputFields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
    }
    """)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    check_translations_register_schema()
