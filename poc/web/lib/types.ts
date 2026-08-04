export type Status =
  | "MATCHED" | "PRODUCT_NOT_FOUND" | "OUT_OF_STOCK" | "SOURCE_ERROR"
  | "confirmed" | "rejected" | "pending";

export interface SellerStatus {
  amazon_in: string;
  flipkart: string;
  meesho: string;
}
export interface Seller {
  seller_id: string;
  store_name: string;
  business_name: string;
  status: SellerStatus;
}
export type SellersResponse = Seller[] | { loading: true } | { error: string };

export interface Candidate {
  store_id: string;
  store_url: string;
  seller_display: string;
  sample_title?: string;
  sample_listing?: string;
  similarity: number;
  n_products?: number;
}
export type ProposeResponse = Candidate[] | { error: string };

export interface RunPreview { sellers: number; products: number; pairs: number; api_calls_est: number; }
export interface SweepPreview { sellers: number; pairs: number; api_calls_est: number; }
export interface JobStatus {
  status: "idle" | "running" | "done" | "error";
  done: number; total: number; run_id?: number | null; error?: string; confirmed?: number;
}

export interface ResultRow {
  naar_seller_id: string; naar_seller_name: string;
  naar_product_title: string; naar_variant_name: string;
  marketplace: string; status: Status;
  naar_selling_price: number | null;
  marketplace_selling_price: number | null;
  marketplace_unit_price: number | null;
  qty_ratio: number | null;
  marketplace_sold_by: string | null;
  other_sellers: string | null;
  listing_url: string | null;
}
export interface RunMeta {
  id: number; started_at: string; finished_at: string; status: string;
  total: number; seller_count: number; product_count: number;
}
export interface ResultsResponse { rows: ResultRow[]; total: number; run: RunMeta | null; }
