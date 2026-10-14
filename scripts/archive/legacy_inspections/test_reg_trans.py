import sys
import json
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def test_register():
    mutation = """
    mutation translationsRegister($resourceId: ID!, $translations: [TranslationInput!]!) {
      translationsRegister(resourceId: $resourceId, translations: $translations) {
        userErrors {
          field
          message
        }
        translations {
          key
          value
          locale
        }
      }
    }
    """
    variables = {
        "resourceId": "gid://shopify/Link/809699115393",
        "translations": [
            {
                "key": "title",
                "value": "Trang chủ",
                "locale": "vi",
                "translatableContentDigest": "1787e77d7217f7b2b48e9a4cb0d5b29b75af4d9e2350fd48d26beb32ac973c93"
            }
        ]
    }
    res = graphql_query(mutation, variables=variables)
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_register()
