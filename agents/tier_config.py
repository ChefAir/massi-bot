"""
Massi-Bot — Tier Configuration (Single Source of Truth)

All tier boundaries, prices, and content descriptions live here.
Imported by conversation_director.py and uncensor_agent.py.
"""

# Tier prices (fixed, never change)
TIER_PRICES = {
    1: 27.38, 2: 36.56, 3: 77.35,
    4: 92.46, 5: 127.45, 6: 200.00,
}

# Director tier boundaries — what level of SUGGESTION is appropriate
DIRECTOR_BOUNDARIES = {
    0: "You haven't shown him anything yet. You're fully clothed. Tease your body through clothes only. Don't suggest removing anything.",
    1: "You've shown a clothed body tease. You can hint at what's underneath but don't suggest removing clothing.",
    2: "You've shown a cleavage tease. Your top is still on. Don't suggest removing it -- that's the next level.",
    3: "You've shown more skin on top. You can be flirty about your upper body. Bottom half is still a mystery.",
    4: "You've shown a lot. You can be very suggestive about your whole body. But don't reference toys or self-touching.",
    5: "You've shown almost everything. Very intimate territory. But no toys or finale references yet.",
    6: "Everything has been shown. Full intimacy mode. No restrictions on what you can reference.",
}

# Uncensor tier boundaries — how much to make text explicit
UNCENSOR_BOUNDARIES = {
    0: "CLOTHED ONLY. No nudity, no body parts, no explicit touching.",
    1: "Clothed tease. Can mention curves through clothing. No nudity.",
    2: "Cleavage/bra visible. Top still on. No topless, no below waist.",
    3: "Topless OK. Top half explicit. Bottom still covered.",
    4: "Full body visible. No toys or self-play.",
    5: "Full nudity + fingering OK. No toys, no climax.",
    6: "No restrictions. Full explicit.",
}

# Validator tier descriptions — what content is FORBIDDEN at each tier
VALIDATOR_DESCRIPTIONS = {
    0: "NOTHING shown yet. Fully clothed. FORBIDDEN: nipples, topless, naked, nude, pussy, fingering, touching herself.",
    1: "Tier 1 SENT: Clothed body tease. FORBIDDEN: nipples visible, topless, nudity below waist, fingering.",
    2: "Tier 2 SENT: Cleavage/bra peeking. Top still ON. FORBIDDEN: top coming off, removing top, nudity below waist.",
    3: "Tier 3 SENT: Topless shown. Top half explicit OK. FORBIDDEN: nudity below waist fully visible, fingering.",
    4: "Tier 4 SENT: Bottoms off. Full body. FORBIDDEN: self-play with toys, climax descriptions.",
    5: "Tier 5 SENT: Full nudity + fingering. FORBIDDEN: toys, dildo, vibrator, climax, orgasm.",
    6: "Tier 6 SENT: Everything shown. No restrictions.",
}
