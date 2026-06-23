/** Server-side backend URL (Render API). Trailing slash stripped. */
export function getBackendApiUrl(): string {
  const url =
    process.env.BACKEND_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    (process.env.NODE_ENV === "production" ? "https://naar-api.onrender.com" : "http://127.0.0.1:8000");

  return url.replace(/\/$/, "");
}
