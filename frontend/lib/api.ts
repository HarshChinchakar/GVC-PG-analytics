import { getToken } from "./session";

/**
 * Server-side client for the FastAPI backend.
 *
 * Every function here runs on the server. `API_BASE_URL` is not prefixed with
 * NEXT_PUBLIC_, so the backend address is never shipped to the browser and the
 * API cannot be called directly from client code.
 */

const API_BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
    // Financial figures must never be served from a cache.
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

// --- types mirroring the backend DTOs --------------------------------

export type LocationCard = {
  id: string; name: string; code: string; city: string | null;
  total_beds: number; occupied: number; available: number;
  occupancy_rate: number; pending_rent: number; pending_count: number;
};

export type AuthUser = {
  id: string; email: string; full_name: string; role: string;
  locations: { id: string; name: string; code: string; city: string | null }[];
};

export type RentRow = {
  rent_record_id: string; resident_id: string; resident_name: string;
  phone: string; flat_number: string | null; bed_label: string | null;
  amount_due: number; status: string; due_date: string;
  paid_on: string | null; marked_by: string | null;
};

export type BedView = {
  id: string; label: string; bed_number: number; status: string;
  is_attached: boolean; default_rent: number;
  resident_id: string | null; resident_name: string | null;
  monthly_rent: number | null; expected_vacant_on: string | null;
};

export type NoticeView = {
  id: string; resident_id: string; resident_name: string; phone: string;
  bed_label: string | null; notice_date: string;
  expected_move_out_date: string; actual_move_out_date: string | null;
  status: string; days_remaining: number | null;
};

export type Dashboard = {
  location_id: string; location_name: string; location_code: string;
  period_year: number; period_month: number; period_label: string;
  available_periods: string[];
  occupancy: {
    total_beds: number; occupied: number; available: number;
    on_notice: number; booked: number; blocked: number; occupancy_rate: number;
  };
  rent: {
    period_label: string; expected_rent: number; collected_rent: number;
    pending_rent: number; collection_rate: number;
    paid_count: number; pending_count: number;
  };
  vacancy: { vacant_beds: number; potential_monthly_loss: number };
  residents: { active: number; notice: number; left: number; living_here: number };
  deposits: { held: number; refunded_to_date: number; approved_unpaid: number } | null;
  pending_payments: RentRow[];
  vacant_beds: BedView[];
  freeing_soon: BedView[];
  upcoming_move_outs: NoticeView[];
  generated_at: string;
};

export type Segment = {
  key: string; label: string;
  beds: number; occupied: number; vacant: number; blocked: number; rentable: number;
  residents: number;
  potential: number; contracted: number; billed: number; collected: number;
  pending: number; vacancy_loss: number; rate_leakage: number;
  occupancy_rate: number; value_occupancy_rate: number;
  rate_realisation: number; contract_realisation: number;
  collection_rate: number; yield_rate: number;
  revpab: number; arpo: number; avg_list_rent: number;
  paid_count: number; pending_count: number;
  sample_beds: string[];
};

export type Dimension = {
  name: string; title: string; question: string; segments: Segment[];
};

export type Analysis = {
  location_id: string; location_name: string; location_code: string;
  period_year: number; period_month: number; period_label: string;
  waterfall: {
    potential: number; vacancy_loss: number; contracted: number;
    rate_leakage: number; billed: number; pending: number; collected: number;
  };
  factors: {
    value_occupancy_rate: number; rate_realisation: number;
    collection_rate: number; yield_rate: number; contract_realisation: number;
  };
  totals: Segment;
  dimensions: Dimension[];
  payment_behaviour: {
    on_or_before_due: number; within_a_week: number;
    within_a_fortnight: number; over_a_fortnight: number;
    average_days_late: number; worst_days_late: number; payments_counted: number;
  };
  trend: {
    period: string; label: string; billed: number; collected: number;
    pending: number; collection_rate: number; yield_rate: number;
  }[];
  callouts: { kind: string; headline: string; detail: string }[];
};

export type SeatState =
  | "occupied_paid" | "occupied_unpaid" | "notice"
  | "booked" | "vacant" | "blocked";

export type SeatResident = {
  id: string; name: string; phone: string; gender: string;
  joined_on: string | null; monthly_rent: number | null;
  rent_status: string | null; paid_on: string | null; free_from: string | null;
  vehicles: { number: string; type: string; make_model: string | null; colour: string | null }[];
};

export type SeatReservation = {
  person_name: string; phone: string; expected_move_in: string;
  days_away: number; token_amount: number; agreed_rent: number | null;
};

export type Seat = {
  id: string; label: string; number: number;
  seat_state: SeatState; tier: string; rent: number; notes: string | null;
  resident: SeatResident | null;
  reservation: SeatReservation | null;
};

export type SeatTier = {
  room_id: string; room_name: string; tier: string; tier_label: string;
  rent: number; beds: Seat[];
};

export type BoardFlat = {
  id: string; flat_number: string; flat_type: string; gender_policy: string;
  tiers: SeatTier[]; bed_count: number; rentable: number;
  filled: number; vacant: number;
};

export type BoardFloor = { number: number; name: string; flats: BoardFlat[] };

export type Board = {
  location_id: string; location_name: string; location_code: string;
  period_year: number; period_month: number; period_label: string;
  floors: BoardFloor[];
  seat_totals: Partial<Record<SeatState, number>>;
  tiers: { tier: string; label: string; beds: number; vacant: number; occupied: number }[];
  gender: { policy: string; beds: number; vacant: number; occupied: number }[];
  generated_at: string;
};

export type VehicleRow = {
  vehicle_number: string; vehicle_type: string;
  make_model: string | null; colour: string | null; notes: string | null;
  resident_id: string; resident_name: string; phone: string;
  resident_status: string;
  bed_label: string | null; flat_number: string | null; floor_name: string | null;
};

export type VehicleSearch = {
  location_id: string; location_name: string; location_code: string;
  query: string; count: number; results: VehicleRow[];
};

export const api = {
  me: () => request<AuthUser>("/auth/me"),
  locations: () => request<LocationCard[]>("/locations"),
  dashboard: (id: string, year?: number, month?: number) => {
    const q = year && month ? `?year=${year}&month=${month}` : "";
    return request<Dashboard>(`/locations/${id}/dashboard${q}`);
  },
  analysis: (id: string, year?: number, month?: number) => {
    const q = year && month ? `?year=${year}&month=${month}` : "";
    return request<Analysis>(`/locations/${id}/analysis${q}`);
  },
  occupancy: (id: string, year?: number, month?: number) => {
    const q = year && month ? `?year=${year}&month=${month}` : "";
    return request<Board>(`/locations/${id}/occupancy${q}`);
  },
  vehicles: (id: string, q?: string) =>
    request<VehicleSearch>(
      `/locations/${id}/vehicles${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    ),
};

export { API_BASE };
