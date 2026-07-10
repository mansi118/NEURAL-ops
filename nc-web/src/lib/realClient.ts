// The real matrix-js-sdk factory — the single boundary where the sdk is imported and adapted to the
// structural `ClientFactory`/`MatrixLike` seam the rest of nc-web is typed against. Kept out of the
// unit-tested path so tests never need the sdk; App wires this in at runtime.
import { createClient } from "matrix-js-sdk";
import type { ClientFactory, MatrixLike } from "./matrixService";

export const realFactory: ClientFactory = (opts) =>
  createClient({
    baseUrl: opts.baseUrl,
    accessToken: opts.accessToken,
    userId: opts.userId,
  }) as unknown as MatrixLike;
