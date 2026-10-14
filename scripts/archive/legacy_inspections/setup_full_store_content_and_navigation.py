import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import urllib.request
import urllib.parse
import urllib.error

def load_env(env_path=".env"):
    config = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

ENV = load_env()
shop = ENV.get("SHOPIFY_STORE_DOMAIN", "rabuta.myshopify.com")
client_id = ENV.get("SHOPIFY_CLIENT_ID")
client_secret = ENV.get("SHOPIFY_CLIENT_SECRET")

def get_token():
    url = f"https://{shop}/admin/oauth/access_token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res["access_token"]

TOKEN = get_token()

def graphql_query(query, variables=None):
    url = f"https://{shop}/admin/api/2026-10/graphql.json"
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("X-Shopify-Access-Token", TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] GraphQL Error: {e}")
        return {}

def create_or_update_page(title, handle, body_html):
    # Check if page exists
    url_get = f"https://{shop}/admin/api/2026-10/pages.json?handle={handle}"
    req = urllib.request.Request(url_get)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    req.add_header("Content-Type", "application/json")
    
    existing_page = None
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("pages", [])
            for p in pages:
                if p["handle"] == handle:
                    existing_page = p
                    break
    except Exception as e:
        pass

    if existing_page:
        pid = existing_page["id"]
        url_put = f"https://{shop}/admin/api/2026-10/pages/{pid}.json"
        payload = {
            "page": {
                "id": pid,
                "title": title,
                "body_html": body_html,
                "published": True
            }
        }
        req_put = urllib.request.Request(url_put, data=json.dumps(payload).encode("utf-8"), method="PUT")
        req_put.add_header("X-Shopify-Access-Token", TOKEN)
        req_put.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req_put) as resp:
            print(f"[+] Updated page '{title}' (/pages/{handle})")
    else:
        url_post = f"https://{shop}/admin/api/2026-10/pages.json"
        payload = {
            "page": {
                "title": title,
                "handle": handle,
                "body_html": body_html,
                "published": True
            }
        }
        req_post = urllib.request.Request(url_post, data=json.dumps(payload).encode("utf-8"), method="POST")
        req_post.add_header("X-Shopify-Access-Token", TOKEN)
        req_post.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req_post) as resp:
            print(f"[+] Created page '{title}' (/pages/{handle})")

# 1. Page Content Definitions (Standard Danish)
PAGES = [
    {
        "title": "Om Rabuta Asian Supermarket",
        "handle": "om-os",
        "body_html": """
        <div class="about-us-container" style="line-height:1.7; font-size:16px;">
            <h2>Velkommen til Rabuta – Dit autentiske asiatiske supermarked i Danmark</h2>
            <p>Hos <strong>Rabuta</strong> brænder vi for at bringe de ægte, rige smage fra hele Asien direkte hjem til dit køkken. Vi tilbyder et bredt og nøje udvalgt sortiment af originale dagligvarer, snacks, nudler, saucer, ris og specialiteter importeret direkte fra <em>Thailand, Vietnam, Japan, Sydkorea, Kina og Taiwan</em>.</p>
            
            <div style="background:#f9f9f9; padding:20px; border-left:4px solid #e53e3e; margin:25px 0;">
                <h3 style="margin-top:0;">Vores kerneværdier:</h3>
                <ul>
                    <li><strong>100% Autenticitet:</strong> Kun originale mærker og råvarer af højeste kvalitet.</li>
                    <li><strong>Hurtig & Sikker Levering:</strong> Vi pakker dine ordrer omhyggeligt og leverer direkte til døren eller din nærmeste pakkeshop.</li>
                    <li><strong>Kundeoplevelse i top:</strong> Tydelig dansk varedeklaration, ingredienser og ernæringstabeller på alle varer.</li>
                </ul>
            </div>
            
            <p>Uanset om du søger klassiske ingredienser til en hjemmelavet pho, ramen, pad thai eller blot vil udforske spændende nye snacks og drikkevarer, står vi altid klar til at hjælpe dig.</p>
        </div>
        """
    },
    {
        "title": "Kontakt os & Butik",
        "handle": "kontakt-os",
        "body_html": """
        <div class="contact-container" style="line-height:1.7; font-size:16px;">
            <h2>Kontakt Rabuta Kundeservice</h2>
            <p>Har du spørgsmål til en ordre, en vare eller ønsker du vejledning om asiatisk madlavning? Du er altid meget velkommen til at kontakte os!</p>
            
            <table style="width:100%; border-collapse:collapse; margin:20px 0; background:#fdfdfd;">
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:10px; font-weight:bold; width:180px;">📧 E-mail:</td>
                    <td style="padding:10px;"><a href="mailto:nmasianshop@gmail.com">nmasianshop@gmail.com</a></td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:10px; font-weight:bold;">🌐 Hjemmeside:</td>
                    <td style="padding:10px;"><a href="https://rabuta.dk">www.rabuta.dk</a></td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:10px; font-weight:bold;">🕒 Svartid:</td>
                    <td style="padding:10px;">Vi besvarer alle henvendelser inden for 24 timer på hverdage.</td>
                </tr>
            </table>

            <h3>Åbningstider for Online Kundeservice:</h3>
            <ul>
                <li>Mandag – Fredag: 09:00 – 18:00</li>
                <li>Lørdag – Søndag: 10:00 – 16:00</li>
            </ul>
        </div>
        """
    },
    {
        "title": "Levering & Fragt",
        "handle": "levering-fragt",
        "body_html": """
        <div class="shipping-container" style="line-height:1.7; font-size:16px;">
            <h2>Hurtig og sikker levering i hele Danmark</h2>
            <p>Hos Rabuta pakker vi dine varer i robuste emballager for at sikre, at dine flasker, saucer og sprøde snacks ankommer i perfekt stand.</p>
            
            <h3>Fragtmuligheder & Priser:</h3>
            <ul>
                <li><strong>GLS / PostNord Pakkeshop:</strong> 39 DKK (Leveringstid: 1-2 hverdage).</li>
                <li><strong>Hjemmelevering:</strong> 59 DKK (Levering direkte til din hoveddør).</li>
                <li><strong>GRATIS FRAGT:</strong> Ved alle køb over <strong>499 DKK</strong> til pakkeshop.</li>
            </ul>

            <h3>Afsendelse af ordrer:</h3>
            <p>Ordrer afgivet inden kl. 14:00 på hverdage afsendes normalt samme dag. Du modtager automatisk et Track & Trace-nummer via e-mail, så du kan følge din pakke hele vejen.</p>
        </div>
        """
    },
    {
        "title": "Handelsbetingelser",
        "handle": "handelsbetingelser",
        "body_html": """
        <div class="terms-container" style="line-height:1.7; font-size:15px;">
            <h2>Handels- og leveringsbetingelser for Rabuta.dk</h2>
            <p><em>Sidst opdateret: Oktober 2026</em></p>
            
            <h3>1. Generelle oplysninger</h3>
            <p>Rabuta.dk drives af Rabuta Asian Supermarket.<br>E-mail: nmasianshop@gmail.com<br>Web: https://rabuta.dk</p>

            <h3>2. Betaling</h3>
            <p>Vi modtager betaling med MobilePay, Dankort, Visa, Mastercard, Apple Pay og Google Pay. Alle priser på hjemmesiden er angivet i danske kroner (DKK) og er inklusive 25% dansk moms.</p>

            <h3>3. Fortrydelsesret (14 dage)</h3>
            <p>Som forbruger har du 14 dages fortrydelsesret på ubrugte, uåbnede tørvarer og ikke-letfordærvelige produkter i henhold til forbrugeraftaleloven. <strong>Bemærk:</strong> I henhold til fødevarelovgivningen bortfalder fortrydelsesretten på fødevarer med brudt forsegling eller varer med begrænset holdbarhed.</p>

            <h3>4. Reklamationsret (24 måneder)</h3>
            <p>Der ydes 24 måneders reklamationsret i henhold til den danske købelov på fabrikations- og materialefejl. Skader opstået ved forkert opbevaring eller håndtering dækkes ikke.</p>

            <h3>5. Klageadgang</h3>
            <p>Hvis du vil klage over dit køb, bedes du rette henvendelse til nmasianshop@gmail.com. Kan vi ikke finde en løsning, kan du indgive en klage til Nævnenes Hus, Toldboden 2, 8800 Viborg via naevneneshus.dk.</p>
        </div>
        """
    },
    {
        "title": "Privatlivspolitik & Cookies",
        "handle": "privatlivspolitik",
        "body_html": """
        <div class="privacy-container" style="line-height:1.7; font-size:15px;">
            <h2>Privatlivs- og persondatapolitik (GDPR)</h2>
            <p>Vi behandler dine personoplysninger med største fortrolighed i overensstemmelse med EU's databeskyttelsesforordning (GDPR) og den danske databeskyttelseslov.</p>
            
            <h3>Hvilke oplysninger indsamler vi?</h3>
            <p>For at du kan handle hos os, har vi brug for følgende oplysninger: Navn, adresse, telefonnummer og e-mailadresse. Vi indsamler og videregiver kun de oplysninger, der er nødvendige for at levere varen til dig (f.eks. til fragtselskaber som GLS/PostNord).</p>

            <h3>Dine rettigheder:</h3>
            <p>Du har altid ret til indsigt i, hvilke oplysninger vi har registreret om dig, samt ret til at få urigtige oplysninger rettet eller slettet. Kontakt os på nmasianshop@gmail.com.</p>
        </div>
        """
    },
    {
        "title": "Retur- og refusionspolitik",
        "handle": "returpolitik",
        "body_html": """
        <div class="refund-container" style="line-height:1.7; font-size:15px;">
            <h2>Retur og Refundering</h2>
            <p>Ønsker du at returnere en vare, bedes du kontakte os på <strong>nmasianshop@gmail.com</strong> med dit ordrenummer, inden du sender varen retur.</p>
            <ul>
                <li>Varen skal returneres i original, uåbnet og ubeskadiget emballage.</li>
                <li>Køber afholder selv de direkte udgifter i forbindelse med returnering af varen.</li>
                <li>Når vi har modtaget og godkendt returvaren, tilbagebetales beløbet til samme betalingsmiddel, som blev anvendt ved købet, inden for 3-5 hverdage.</li>
            </ul>
        </div>
        """
    }
]

# 2. GraphQL Menu Updates
def setup_menus():
    print("\n[*] Setting up Main Menu & Footer Menu via GraphQL Navigation API...")
    
    # Query existing menus
    get_menus_query = """
    {
      menus(first: 10) {
        edges {
          node {
            id
            handle
            title
            items {
              id
              title
              url
            }
          }
        }
      }
    }
    """
    res = graphql_query(get_menus_query)
    menus = res.get("data", {}).get("menus", {}).get("edges", [])
    
    main_menu_id = None
    footer_menu_id = None
    
    for m in menus:
        node = m["node"]
        if node["handle"] == "main-menu":
            main_menu_id = node["id"]
        elif node["handle"] == "footer":
            footer_menu_id = node["id"]

    print(f"    - Found Main Menu ID: {main_menu_id}")
    print(f"    - Found Footer Menu ID: {footer_menu_id}")

    # Main Menu Items
    main_items = [
        {"title": "Hjem", "type": "FRONTPAGE", "url": "/"},
        {"title": "Nudler", "type": "COLLECTION", "url": "/collections/nudler"},
        {"title": "Snacks", "type": "COLLECTION", "url": "/collections/snacks"},
        {"title": "Saucer & Sojasauce", "type": "COLLECTION", "url": "/collections/saucer-sojasauce"},
        {"title": "Krydderier & Karry", "type": "COLLECTION", "url": "/collections/krydderier-karry"},
        {"title": "Drikkevarer", "type": "COLLECTION", "url": "/collections/drikkevarer-vin"},
        {"title": "Ris, Mel & Tørvarer", "type": "COLLECTION", "url": "/collections/ris-mel-torvarer"},
        {"title": "Andre asiatiske varer", "type": "COLLECTION", "url": "/collections/andre-asiatiske-varer"},
        {"title": "Om os", "type": "PAGE", "url": "/pages/om-os"},
        {"title": "Kontakt", "type": "PAGE", "url": "/pages/kontakt-os"}
    ]

    # Footer Menu Items
    footer_items = [
        {"title": "Om Rabuta", "type": "PAGE", "url": "/pages/om-os"},
        {"title": "Kontakt os", "type": "PAGE", "url": "/pages/kontakt-os"},
        {"title": "Levering & Fragt", "type": "PAGE", "url": "/pages/levering-fragt"},
        {"title": "Handelsbetingelser", "type": "PAGE", "url": "/pages/handelsbetingelser"},
        {"title": "Returpolitik", "type": "PAGE", "url": "/pages/returpolitik"},
        {"title": "Privatlivspolitik", "type": "PAGE", "url": "/pages/privatlivspolitik"}
    ]

    update_menu_mutation = """
    mutation menuUpdate($id: ID!, $title: String!, $handle: String!, $items: [MenuItemUpdateInput!]!) {
      menuUpdate(id: $id, title: $title, handle: $handle, items: $items) {
        menu {
          id
          title
          items {
            title
            url
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    create_menu_mutation = """
    mutation menuCreate($title: String!, $handle: String!, $items: [MenuItemCreateInput!]!) {
      menuCreate(title: $title, handle: $handle, items: $items) {
        menu {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    # Update/Create Main Menu
    if main_menu_id:
        res_main = graphql_query(update_menu_mutation, {
            "id": main_menu_id,
            "title": "Main menu",
            "handle": "main-menu",
            "items": [{"title": i["title"], "type": i["type"], "url": i["url"]} for i in main_items]
        })
        print("    [+] Main Menu Updated Successfully!")
    else:
        res_main = graphql_query(create_menu_mutation, {
            "title": "Main menu",
            "handle": "main-menu",
            "items": [{"title": i["title"], "type": i["type"], "url": i["url"]} for i in main_items]
        })
        print("    [+] Main Menu Created Successfully!")

    # Update/Create Footer Menu
    if footer_menu_id:
        res_foot = graphql_query(update_menu_mutation, {
            "id": footer_menu_id,
            "title": "Footer menu",
            "handle": "footer",
            "items": [{"title": i["title"], "type": i["type"], "url": i["url"]} for i in footer_items]
        })
        print("    [+] Footer Menu Updated Successfully!")
    else:
        res_foot = graphql_query(create_menu_mutation, {
            "title": "Footer menu",
            "handle": "footer",
            "items": [{"title": i["title"], "type": i["type"], "url": i["url"]} for i in footer_items]
        })
        print("    [+] Footer Menu Created Successfully!")

def main():
    print("=========================================================")
    print("     AUTO CONFIGURING PAGES & MENUS ON SHOPIFY STORE     ")
    print("=========================================================")
    
    # 1. Create Pages
    print("\n[*] Creating & Publishing Standard Danish Pages...")
    for p in PAGES:
        create_or_update_page(p["title"], p["handle"], p["body_html"])

    # 2. Setup Menus
    setup_menus()

    print("\n=========================================================")
    print("🎉 STORE SETUP AUTOMATION COMPLETED SUCCESSFULLY!")
    print("=========================================================")

if __name__ == "__main__":
    main()
