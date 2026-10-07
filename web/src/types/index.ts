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

export interface Venue {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  location: Location;
}

export interface EventArtist {
  id: string;
  name: string;
  image_url: string | null;
  genres: string[];
  billing: number; // 0 is the headliner
}

export interface EventDetail {
  id: string;
  title: string | null;
  starts_at: string;
  doors_at: string | null;
  on_sale_at: string | null;
  price_min_cents: number | null;
  price_max_cents: number | null;
  currency: string | null;
  status: string;
  source: string;
  source_url: string | null;
  image_url: string | null;
  venue: Venue;
  artists: EventArtist[];
}

export interface UpcomingShow {
  event_id: string;
  title: string | null;
  starts_at: string;
  venue_name: string;
  venue_city: string | null;
  price_min_cents: number | null;
  price_max_cents: number | null;
  distance_m: number | null; // null when the user has no home location
  dismissed: boolean;
}

export interface ArtistDetail extends ArtistSummary {
  upcoming: UpcomingShow[];
  similar: ArtistSummary[];
}
