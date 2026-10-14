import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN")
url = "https://rabuta.myshopify.com/admin/api/2024-01/graphql.json"

def gql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

market_id = "gid://shopify/Market/98935341441"
web_presence_id = "gid://shopify/MarketWebPresence/70183223681"

mutation = """
mutation MarketUpdate($id: ID!, $input: MarketUpdateInput!) {
  marketUpdate(id: $id, input: $input) {
    market {
      id
      name
      webPresence {
        id
        domain {
          host
        }
        defaultLocale {
          locale
          name
        }
        alternateLocales {
          locale
          name
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

variables = {
    "id": market_id,
    "input": {
        "webPresencesToAdd": [web_presence_id]
    }
}

res = gql(mutation, variables)
print("Market Update Result:", json.dumps(res, indent=2))
