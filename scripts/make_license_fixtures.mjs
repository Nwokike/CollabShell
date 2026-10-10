// Mint the license test fixtures: a throwaway P-256 keypair signs the same
// v1.<b64url payload>.<b64url raw r||s> shape the Worker emits via WebCrypto.
// Run with: node scripts/make_license_fixtures.mjs
// Output: tests/license_fixtures.py

import { webcrypto } from "node:crypto";
import { writeFileSync } from "node:fs";

const APP = "ng.kiri.collabshell";
const IAT = 1758600000; // 2025-09-22, fixed so fixtures never expire-by-now

const b64url = (buf) =>
  Buffer.from(buf)
    .toString("base64")
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");

const subtle = webcrypto.subtle;

const key = await subtle.generateKey(
  { name: "ECDSA", namedCurve: "P-256" },
  true,
  ["sign", "verify"],
);
const PUBLIC_KEY = b64url(await subtle.exportKey("spki", key.publicKey));

const TOKENS = {};
const mint = async (name, over) => {
  const claims = {
    iss: "license.kiri.ng",
    v: 1,
    ent: "fixture-entitlement",
    app: APP,
    product: "lifetime",
    scope: "universal",
    mode: "one_time",
    status: "active",
    paid_through: null,
    iat: IAT,
    exp: null,
    ...over,
  };
  const payload = b64url(Buffer.from(JSON.stringify(claims), "utf8"));
  const sig = await subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    key.privateKey,
    Buffer.from(payload, "utf8"),
  );
  TOKENS[name] = `v1.${payload}.${b64url(sig)}`;
};

await mint("LIFETIME");
await mint("YEARLY_ACTIVE", {
  product: "yearly",
  mode: "recurring",
  paid_through: 4102444800,
  exp: 4102444800, // 2100-01-01: must outlive wall-clock tests
});
await mint("EXPIRED", { status: "expired", exp: 1700000000 });
await mint("REVOKED", { status: "revoked" });
await mint("GRACE", { status: "grace", exp: 4102444800 });
// Universal scope is the default for every Kiri product, and the Worker
// re-mints a token with the REQUESTING app's id on every restore — so a
// token whose app claim is another Kiri app must still verify here.
await mint("OTHER_APP", { app: "ng.kiri.ktvplayer", scope: "universal" });
// The one case that does gate: a per-app scope list.
await mint("SCOPED_OUT", { app: "ng.kiri.ktvplayer", scope: ["ng.kiri.ktvplayer"] });
await mint("BAD_ISSUER", { iss: "evil.example" });
await mint("UNSUPPORTED_VERSION", { v: 2 });
await mint("EXPIRING_SOON", { exp: 1758600060 });

const lines = [
  '"""License test fixtures: real ECDSA P-256 signatures for ng.kiri.collabshell.',
  "",
  "Minted by scripts/make_license_fixtures.mjs (Node WebCrypto), NOT invented by",
  "this suite: the private key is throwaway and discarded, so these are genuine",
  "signatures against a real P-256 keypair — the same shape the license Worker",
  'emits. Regenerate with: node scripts/make_license_fixtures.mjs',
  '"""',
  "",
  "",
  `PUBLIC_KEY = ${JSON.stringify(PUBLIC_KEY)}`,
  "",
  "TOKENS = {",
  ...Object.entries(TOKENS).map(
    ([name, token]) => `    ${JSON.stringify(name)}: ${JSON.stringify(token)},`,
  ),
  "}",
];

writeFileSync("tests/license_fixtures.py", lines.join("\n") + "\n");
console.log(
  "wrote tests/license_fixtures.py with",
  Object.keys(TOKENS).length,
  "tokens",
);
