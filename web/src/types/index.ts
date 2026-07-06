// Shared TypeScript types mirroring the gateway's response schemas.

export interface Location {
  lat: number;
  lon: number;
}

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  home_location: Location | null;
  travel_radius_m: number;
  alert_email: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  created_at: string;
}

export interface DevAuthResponse {
  token: string;
  user: User;
}

export interface UserUpdate {
  display_name?: string | null;
  home_location?: Location | null;
  travel_radius_m?: number;
  alert_email?: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
}

export interface FeedItem {
  event_id: string;
  title: string | null;
  starts_at: string;
  status: string;
  price_min_cents: number | null;
  price_max_cents: number | null;
  source_url: string | null;
  image_url: string | null;
  venue_name: string;
  venue_city: string | null;
  venue_lat: number;
  venue_lon: number;
  distance_m: number;
  artist_id: string;
  artist_name: string;
  artist_image_url: string | null;
  artist_genres: string[];
  score: number;
}

export interface FeedPage {
  items: FeedItem[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface FeedFilters {
  dateRange: [string, string] | null;
  genres: string[];
  maxDistance: number | null; // meters
  maxPrice: number | null; // cents
}

export interface ArtistSummary {
  id: string;
  name: string;
  image_url: string | null;
  genres: string[];
  followed: boolean;
}
