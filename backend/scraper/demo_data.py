"""Demo catalog — mirrors naar.io/shop product shape until live scrape runs."""

from scraper.platform_urls import flipkart_search_url, meesho_search_url, product_url

DEMO_PRODUCTS = [
    {
        "sku": "NK-HT-001",
        "name": "Handloom Cotton Kurta",
        "variant": "M / Indigo",
        "price": 1899.0,
        "url": "https://naar.io/shop",
        "category": "Fashion",
        "image": None,
        "source": "demo",
    },
    {
        "sku": "NK-TP-014",
        "name": "Terracotta Planter Set",
        "variant": "3pc",
        "price": 1299.0,
        "url": "https://naar.io/shop",
        "category": "Home Essentials",
        "image": None,
        "source": "demo",
    },
    {
        "sku": "NK-BD-022",
        "name": "Brass Diya Collection",
        "variant": "Gold",
        "price": 749.0,
        "url": "https://naar.io/shop",
        "category": "Home Essentials",
        "image": None,
        "source": "demo",
    },
    {
        "sku": "NK-BS-008",
        "name": "Block Print Bedsheet",
        "variant": "King",
        "price": 2199.0,
        "url": "https://naar.io/shop",
        "category": "Home Essentials",
        "image": None,
        "source": "demo",
    },
    {
        "sku": "NK-JT-031",
        "name": "Jute Tote Bag",
        "variant": "Natural",
        "price": 599.0,
        "url": "https://naar.io/shop",
        "category": "Fashion Accessories",
        "image": None,
        "source": "demo",
    },
]

def _amazon_demo(title: str, pid: str, price: float) -> dict:
    return {
        "platform": "amazon",
        "platform_id": pid,
        "title": title,
        "price": price,
        "url": product_url("amazon", title),
        "is_search_link": True,
    }


DEMO_CANDIDATES = {
    "amazon": [
        _amazon_demo("Handloom Cotton Kurta Indigo Medium", "demo-kurta", 1670.0),
        _amazon_demo("Terracotta Planter Set of 3", "demo-planter", 1299.0),
        _amazon_demo("Brass Diya Collection Gold Finish", "demo-diya", 749.0),
        _amazon_demo("King Size Block Print Cotton Bedsheet", "demo-bedsheet", 2089.0),
        _amazon_demo("Natural Jute Tote Shopping Bag", "demo-tote", 599.0),
    ],
    "flipkart": [
        {
            "platform": "flipkart",
            "platform_id": "demo-planter",
            "title": "Terracotta Planter Set 3 Piece",
            "price": 1403.0,
            "url": flipkart_search_url("Terracotta Planter Set 3 Piece"),
            "is_search_link": True,
        },
        {
            "platform": "flipkart",
            "platform_id": "demo-bedsheet",
            "title": "Block Print Bedsheet King Size",
            "price": 2089.0,
            "url": flipkart_search_url("Block Print Bedsheet King Size"),
            "is_search_link": True,
        },
        {
            "platform": "flipkart",
            "platform_id": "demo-kurta",
            "title": "Handloom Cotton Kurta M Indigo",
            "price": 1899.0,
            "url": flipkart_search_url("Handloom Cotton Kurta M Indigo"),
            "is_search_link": True,
        },
    ],
    "meesho": [
        {
            "platform": "meesho",
            "platform_id": "demo-kurta",
            "title": "Cotton Kurta Handloom Indigo M",
            "price": 1749.0,
            "url": meesho_search_url("Cotton Kurta Handloom Indigo M"),
            "is_search_link": True,
        },
        {
            "platform": "meesho",
            "platform_id": "demo-diya",
            "title": "Brass Diya Set Gold",
            "price": 899.0,
            "url": meesho_search_url("Brass Diya Set Gold"),
            "is_search_link": True,
        },
        {
            "platform": "meesho",
            "platform_id": "demo-tote",
            "title": "Jute Tote Bag Natural",
            "price": 539.0,
            "url": meesho_search_url("Jute Tote Bag Natural"),
            "is_search_link": True,
        },
    ],
    "seller": [
        {
            "platform": "seller",
            "platform_id": "seller-diya",
            "title": "Brass Diya Collection",
            "price": 861.0,
            "url": "https://naar.io/shop",
            "seller_name": "Artisan Store",
            "is_search_link": True,
        },
        {
            "platform": "seller",
            "platform_id": "seller-kurta",
            "title": "Handloom Kurta Indigo",
            "price": 1999.0,
            "url": "https://naar.io/shop",
            "seller_name": "Weave Co",
            "is_search_link": True,
        },
    ],
}
