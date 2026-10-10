"""Build channel marker.

``direct`` (the committed default) is the GitHub APK / Windows / Linux build:
full app with Kiri premium checkout.

``play`` is the Android App Bundle that ships to Google Play: free tier with
ads and NO premium of any kind. The Play AAB build job overwrites this file's
single line, so the channel is decided by the artifact rather than at runtime.

Ported verbatim in shape from ktv-player/src/core/channel.py — the marker file
must stay exactly one line for the workflow's `echo ... >` to work.
"""

# Build channel: "direct" (GitHub/desktop, premium enabled) or "play"
# (Google Play AAB, free tier with ads, no premium).
CHANNEL = "direct"
