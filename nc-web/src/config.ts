// Build/env config. The homeserver base URL is the one knob; defaults to the live NeuralEdge Synapse
// and can be overridden at build time (VITE_MATRIX_BASE_URL). No secrets here — auth is Matrix login.
export const MATRIX_BASE_URL: string =
  import.meta.env.VITE_MATRIX_BASE_URL ?? "https://matrix.neuraledge.in";

export const APP_NAME = "NeuralChat";
