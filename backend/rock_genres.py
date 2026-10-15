"""Rock-genre allowlist for the Phase 1 crawl boundary.

The crawler only enqueues a band if at least one of its MusicBrainz genre tags
is in ROCK_GENRES. This keeps a snowball crawl from wandering out of rock and
into the entire history of recorded music via session players and one-off
collaborations.

Why an explicit set instead of `"rock" in name`:
  - Substring matching LETS IN reggae ("lovers rock", "rocksteady").
  - It EXCLUDES real rock forms whose names lack the word -- grunge, britpop,
    shoegaze, new wave, the metal family. Those are the genres our own seed
    bands carry (Nirvana is tagged "grunge", not "rock"), so a substring filter
    would refuse to crawl the neighborhood we started from.

Source: MusicBrainz genre vocabulary (2173 genres total), fetched from
/ws/2/genre/all. 89 genres contain "rock" (minus the reggae false positives
below); 24 more are rock forms without "rock" in the name.

Judgment calls encoded here (revisit if the crawl feels too wide/narrow):
  - Metal IS included -- Sabbath, Deep Purple, and Rainbow are in the seed, so
    dropping metal would sever part of our own graph. Remove the METAL block if
    you decide metal is a separate lineage.
  - "lovers rock" and "rocksteady" are EXCLUDED as reggae/Jamaican.
  - "crack rock steady" (a punk coinage) is left out as borderline.

Matching note: compare case-insensitively. MusicBrainz genre names are
lowercase UTF-8 -- decode responses as UTF-8 or accented names corrupt.
"""

# Genres whose name contains "rock" (reggae false positives already removed).
_ROCK_NAMED = {
    "acid rock", "acoustic rock", "afro rock", "alpenrock", "alternative rock",
    "anatolian rock", "arena rock", "art rock", "asian rock", "bard rock",
    "beat rock", "blues rock", "boogie rock", "british folk rock", "celtic rock",
    "christian rock", "classic rock", "comedy rock", "country rock", "dance-rock",
    "deathrock", "desert rock", "electronic rock", "experimental rock",
    "folk rock", "frat rock", "funk rock", "garage rock", "garage rock revival",
    "geek rock", "glam rock", "gothic rock", "hard rock", "heartland rock",
    "indie rock", "indorock", "industrial rock", "instrumental rock", "j-rock",
    "jazz rock", "krautrock", "könsrock", "latin rock", "machine rock",
    "mainstream rock", "math rock", "medieval rock", "neo-progressive rock",
    "neo-rockabilly", "noise rock", "occult rock", "piano rock", "pop rock",
    "post-rock", "progressive rock", "psychedelic rock", "pub rock", "punk rock",
    "raga rock", "rap rock", "reggae rock", "rock", "rock and roll",
    "rock andaluz", "rock andino", "rock kapak", "rock musical", "rock opera",
    "rock rural", "rock urbano", "rock urbano mexicano", "rockabilly",
    "roots rock", "samba-rock", "slacker rock", "sleaze rock", "soft rock",
    "southern rock", "space rock", "space rock revival", "stoner rock",
    "sufi rock", "surf rock", "swamp rock", "symphonic rock", "tropical rock",
    "viking rock", "yacht rock", "zamrock",
}

# Rock forms with no "rock" in the name.
_ROCK_UNNAMED = {
    "britpop", "dream pop", "emo", "grunge", "jangle pop", "madchester",
    "new wave", "no wave", "post-grunge", "post-hardcore", "post-punk",
    "power pop", "riot grrrl", "screamo", "shoegaze", "slowcore", "surf",
}

# The metal family. Remove this block to treat metal as a separate lineage.
_METAL = {
    "alternative metal", "doom metal", "grindcore", "heavy metal", "metalcore",
    "nu metal", "thrash metal",
}

ROCK_GENRES = _ROCK_NAMED | _ROCK_UNNAMED | _METAL


def is_rock(genres):
    """True if any genre tag is in the rock allowlist (case-insensitive)."""
    return any(g.strip().lower() in ROCK_GENRES for g in genres)
