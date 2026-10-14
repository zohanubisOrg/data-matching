import urllib.request
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
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

query = """
{
  themes(first: 10, roles: [MAIN]) {
    nodes {
      id
      name
      role
    }
  }
}
"""

res = gql(query)
print("Main Theme:", json.dumps(res, indent=2))
