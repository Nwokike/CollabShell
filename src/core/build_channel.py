"""Which distribution channel this build is for.

Two values exist:

- ``"direct"`` — every build by default: direct APKs, desktop, web. Premium
  is sold through the Kiri License Worker (and Play Billing rows appear if
  the store ever lists products for this package).
- ``"play"`` — the AAB uploaded to Google Play. Premium purchase UI does
  not exist on it: Google requires a Google Payments merchant profile to
  sell in-app, which no account available to us has yet. Play users get
  the free tier (50 credits a day, ads) until a merchant account exists.

The workflow's AAB job rewrites this one line before building, so the
policy is baked into the artifact — nothing is decided at runtime.
"""

CHANNEL = "direct"

__all__ = ["CHANNEL"]
