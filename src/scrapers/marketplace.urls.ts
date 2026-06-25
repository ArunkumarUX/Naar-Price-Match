export function marketplaceSearchUrl(platform: "amazon" | "flipkart" | "meesho", query: string): string {
  const q = encodeURIComponent(query);
  if (platform === "amazon") return `https://www.amazon.in/s?k=${q}`;
  if (platform === "flipkart") return `https://www.flipkart.com/search?q=${q}`;
  return `https://www.meesho.com/search?q=${q}`;
}

export function marketplaceSearchFallback(
  platform: "amazon" | "flipkart" | "meesho",
  query: string,
) {
  return {
    title: query,
    price: null,
    url: marketplaceSearchUrl(platform, query),
    is_search_link: true,
    platformId: `${platform}-search`,
  };
}
