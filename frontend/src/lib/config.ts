export const FIXTURE_MODE = process.env.NEXT_PUBLIC_FIXTURE_MODE === "1";
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = `${API_URL.replace(/^http/, "ws")}/ws`;
export const FIXTURE_SEED = 42;
