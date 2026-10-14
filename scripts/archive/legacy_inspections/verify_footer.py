import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def verify_footer():
    theme_id = "189930996097"
    footer_res_id = f"gid://shopify/OnlineStoreThemeSectionGroup/footer-group?theme_id={theme_id}"
    q = f"""
    {{
      translatableResource(resourceId: "{footer_res_id}") {{
        translatableContent {{
          key
          value
        }}
        da: translations(locale: "da") {{
          key
          value
        }}
        vi: translations(locale: "vi") {{
          key
          value
        }}
      }}
    }}
    """
    res = graphql_query(q)
    node = res.get("data", {}).get("translatableResource", {})
    print("Footer Theme Section Translations:")
    tc = node.get("translatableContent", [])
    da_list = {x["key"]: x["value"] for x in node.get("da", [])}
    vi_list = {x["key"]: x["value"] for x in node.get("vi", [])}
    for item in tc:
        k = item["key"]
        print(f"  [{k}]")
        print(f"    Orig: {item['value']}")
        print(f"    DA:   {da_list.get(k, '(none)')}")
        print(f"    VI:   {vi_list.get(k, '(none)')}")

if __name__ == "__main__":
    verify_footer()
