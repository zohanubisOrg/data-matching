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

# 1. First let's check current shop primary domain and all domains
shop_info = gql("""
{
  shop {
    id
    primaryDomain {
      id
      host
    }
  }
  shopLocales {
    locale
    name
    primary
    published
  }
  markets(first: 5) {
    nodes {
      id
      name
      primary
    }
  }
}
""")
print("Shop Info:", json.dumps(shop_info, indent=2))

# 2. Try creating a WebPresence for rabuta.dk with defaultLocale 'en' and alternateLocales ['da', 'th', 'vi']
# Or defaultLocale 'da' and alternateLocales ['en', 'th', 'vi']
# Note: shopLocales has 'en' as primary: true
domain_id = shop_info["data"]["shop"]["primaryDomain"]["id"]
market_id = shop_info["data"]["markets"]["nodes"][0]["id"]

mutation = """
mutation WebPresenceCreate($input: WebPresenceCreateInput!) {
  webPresenceCreate(input: $input) {
    webPresence {
      id
      subfolderSuffix
      alternateLocales {
        locale
        name
      }
      defaultLocale {
        locale
        name
      }
      domain {
        id
        host
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
    "input": {
        "domainId": domain_id,
        "defaultLocale": "en",
        "alternateLocales": ["da", "th", "vi"]
    }
}

res = gql(mutation, variables)
print("Create WebPresence Result:", json.dumps(res, indent=2))

if res.get("data", {}).get("webPresenceCreate", {}).get("webPresence"):
    wp_id = res["data"]["webPresenceCreate"]["webPresence"]["id"]
    print(f"Created WebPresence ID: {wp_id}. Now attaching to Market {market_id}...")
    
    m_update = """
    mutation MarketUpdate($id: ID!, $input: MarketUpdateInput!) {
      marketUpdate(id: $id, input: $input) {
        market {
          id
          name
          webPresence {
            id
            defaultLocale {
              locale
            }
            alternateLocales {
              locale
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
    res_m = gql(m_update, {"id": market_id, "input": {"webPresencesToAdd": [wp_id]}})
    print("Market Update Result:", json.dumps(res_m, indent=2))
