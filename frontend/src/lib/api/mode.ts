// The replay build (`npm run build:replay`, Vite mode "replay") shows recorded runs and needs no
// backend. Recorded data ships only in that build (vite.config.ts); the normal build contains the
// small replay adapter as an unused chunk that it never loads.
export const IS_REPLAY = import.meta.env.MODE === "replay";
