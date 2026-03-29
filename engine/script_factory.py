"""
Massi-Bot Bot Engine - Script Factory v2
Generates complete script arcs wired to the 6-tier pricing ladder.

KEY CHANGES from v1:
  - 6 PPV drops per script (one per tier) instead of 3 random-priced drops
  - Fixed pricing: $27.38 → $36.56 → $77.35 → $92.46 → $127.45 → $200
  - Full ladder per script = $561.20
  - Tier-specific messaging and captions at every level
  - Shared content bundles across all 10 personas (content is persona-agnostic)
  - Per-subscriber dedup: no sub sees the same bundle twice

CONTENT ARCHITECTURE:
  12 scripts × 6 tiers = 72 content bundles (shared across personas)
  Model films 72 sets of 3-4 photos + 1-2 videos
  Changes outfit 12 times (once per script), may change locations
  Content is generic (tight clothes, lingerie) — works for all personas
  Only the messaging/voice/captions change per persona

SCRIPT STRUCTURE (17 steps):
  1. INTRO            — Setup / context
  2. TEASE            — Flirty warm-up
  3. HEAT_BUILD       — Dirty talk escalation
  4. PPV_DROP         — Tier 1: $27.38  Full Body Tease (clothed)
  5. REACTION         — Dirty talk bridge → Tier 2
  6. ESCALATION       — Tier 2: $36.56  Top Tease
  7. REACTION         — Dirty talk bridge → Tier 3
  8. ESCALATION       — Tier 3: $77.35  Top Reveal
  9. REACTION         — Dirty talk bridge → Tier 4
  10. ESCALATION      — Tier 4: $92.46  Bottom Reveal
  11. REACTION        — Dirty talk bridge → Tier 5
  12. ESCALATION      — Tier 5: $127.45 Full Explicit
  13. REACTION        — Dirty talk bridge → Tier 6
  14. ESCALATION      — Tier 6: $200    Climax
  15. CUSTOM_TEASE    — Custom content pitch
  16. COOLDOWN        — Post-session GFE care
"""

from typing import List, Dict, Optional, Tuple
from models import Script, ScriptStep, ScriptPhase, SubType, NicheType
from avatars import AvatarConfig, ALL_AVATARS
from onboarding import ContentTier, TIER_CONFIG, get_tier_price, get_full_ladder_price
from theme_templates_extended import EXTENDED_THEMES
from avatar_tier_captions import AVATAR_TIER_CAPTIONS


# ═══════════════════════════════════════════════════════════════
# 6-TIER LADDER (imported from onboarding, defined here for reference)
# ═══════════════════════════════════════════════════════════════

TIER_LADDER = [
    ContentTier.TIER_1_BODY_TEASE,     # $27.38
    ContentTier.TIER_2_TOP_TEASE,      # $36.56
    ContentTier.TIER_3_TOP_REVEAL,     # $77.35
    ContentTier.TIER_4_BOTTOM_REVEAL,  # $92.46
    ContentTier.TIER_5_FULL_EXPLICIT,  # $127.45
    ContentTier.TIER_6_CLIMAX,         # $200.00
]

TIER_PRICES = [get_tier_price(t) for t in TIER_LADDER]
FULL_LADDER_TOTAL = get_full_ladder_price()  # $561.20


# ═══════════════════════════════════════════════════════════════
# TIER-SPECIFIC MESSAGING TEMPLATES
# ═══════════════════════════════════════════════════════════════
# These are the default lead-in messages and captions per tier.
# Theme-specific overrides can replace any of these.

DEFAULT_TIER_LEAD_INS = {
    ContentTier.TIER_1_BODY_TEASE: [
        "okay fine you win… but you asked for it 😈",
        "don't say I didn't warn you…",
        "I can't believe I'm about to send this but here goes",
    ],
    ContentTier.TIER_2_TOP_TEASE: [
        "okay that was just a preview… this one shows a little more 😏",
        "you earned a peek at what's underneath… don't say I'm not generous",
        "this one is gonna make you wish you were here pulling this off yourself 😈",
    ],
    ContentTier.TIER_3_TOP_REVEAL: [
        "okay no more teasing… you're about to see everything on top 🥵",
        "I've been holding back but I can't anymore… you did this to me",
        "this is the one where the shirt comes all the way off 😈",
    ],
    ContentTier.TIER_4_BOTTOM_REVEAL: [
        "mmm okay now it's getting real… the bottom half is your reward 😏",
        "you've been so good to me tonight I have to show you more",
        "I put my top back on but the bottoms? those are gone 🥵",
    ],
    ContentTier.TIER_5_FULL_EXPLICIT: [
        "okay this is the one… everything off. nothing hidden. just me 😈",
        "you've earned the full thing and I'm not holding back at all",
        "this is me at my most vulnerable and I'm only showing YOU 🥵",
    ],
    ContentTier.TIER_6_CLIMAX: [
        "this is it baby… the final one. I went all out and I can't even describe it 😈",
        "I used everything in my drawer for this one and you're gonna lose your mind",
        "this is the one that made me finish… and I was thinking about you the entire time 🥵",
    ],
}

DEFAULT_TIER_CAPTIONS = {
    ContentTier.TIER_1_BODY_TEASE: [
        "I couldn't help myself… this is your fault 😈",
        "just a little tease… but trust me there's so much more where this came from",
        "this is what you do to me… and I'm just getting started 😏",
        "be honest… can you handle more of this? because I have a lot more",
    ],
    ContentTier.TIER_2_TOP_TEASE: [
        "the shirt is coming down… but not all the way. yet. 😏",
        "just a little peek at what's underneath… you want the rest?",
        "this one's a preview of what happens next if you keep being good",
    ],
    ContentTier.TIER_3_TOP_REVEAL: [
        "no more hiding… this is all for you 🥵",
        "the top is off and I couldn't wait to show you",
        "I took it all off up top and I don't regret a thing",
    ],
    ContentTier.TIER_4_BOTTOM_REVEAL: [
        "top's back on but the bottoms disappeared 😈",
        "I saved this angle just for you… you're welcome",
        "the bottoms came off and I let the camera see everything",
    ],
    ContentTier.TIER_5_FULL_EXPLICIT: [
        "everything off. just me. playing. for you. 🥵",
        "fully unclothed and I can't stop touching myself thinking about you",
        "nothing left to hide… this is all of me 😈",
    ],
    ContentTier.TIER_6_CLIMAX: [
        "the grand finale 😈 toys. climax. everything. I screamed your name.",
        "I went all the way and filmed every second for you 🥵",
        "this is my best one… the finish is going to destroy you",
    ],
}

# Dirty talk bridges between tiers (sell-dirty talk-sell loop)
DEFAULT_TIER_BRIDGES = {
    # After Tier 1 → before Tier 2
    ContentTier.TIER_2_TOP_TEASE: [
        "told you 😈 and that was just tier one… it gets so much better",
        "mmm you liked that? baby that was nothing… wait til you see what comes next 🥵",
        "I could tell you'd be into that… but I'm not done with you yet 😏",
    ],
    # After Tier 2 → before Tier 3
    ContentTier.TIER_3_TOP_REVEAL: [
        "the tease is over… now you get the real thing 😈",
        "you've been so patient and I'm about to reward you big time",
        "okay I can't tease anymore I literally need to show you 🥵",
    ],
    # After Tier 3 → before Tier 4
    ContentTier.TIER_4_BOTTOM_REVEAL: [
        "top half was just the appetizer… you ready for the main course? 😏",
        "you thought that was it? baby we're only halfway there",
        "I love that you keep coming back… this next one is my favorite 😈",
    ],
    # After Tier 4 → before Tier 5
    ContentTier.TIER_5_FULL_EXPLICIT: [
        "okay no more teasing no more hiding… you're about to see everything 😈",
        "you've proven you deserve the full thing and I'm not holding back",
        "this is where it gets real… are you ready? because I am 🥵",
    ],
    # After Tier 5 → before Tier 6
    ContentTier.TIER_6_CLIMAX: [
        "you've seen me undressed but you haven't seen me finish… that changes now 😈",
        "okay this is the one I was saving… the grand finale. you earned every second of this",
        "I've been building to this all night and I literally can't hold it in anymore 🥵",
    ],
}


# ═══════════════════════════════════════════════════════════════
# THEME TEMPLATES - Per-theme messaging for each script phase
# ═══════════════════════════════════════════════════════════════
# Each theme can optionally include tier-specific captions/lead-ins.
# If missing, the factory uses DEFAULT_TIER_* templates above.
#
# OPTIONAL tier-specific keys:
#   "tier_captions": { ContentTier → [captions] }
#   "tier_lead_ins": { ContentTier → [lead-in messages] }
#   "tier_bridges":  { ContentTier → [bridge/dirty talk messages] }

THEME_TEMPLATES = {
    # ─── GIRL BOSS THEMES ───
    "stressed_after_meeting": {
        "description": "Just got out of a stressful meeting, needs to unwind",
        "intro": [
            "ugh I just had the most draining meeting of my life 😩 I need someone to vent to",
            "okay so my business partner is driving me insane and I need a distraction",
            "I literally just closed my laptop and I'm laying on the couch drained",
        ],
        "tease": [
            "I'm still in my work clothes but honestly I wanna rip them off and just lay here",
            "the only good part of working from home is nobody sees what I change into after 😏",
            "I switched into something more comfortable and by comfortable I mean barely anything lol",
        ],
        "heat_build": [
            "you know what the best stress relief is? and no I don't mean yoga 😈",
            "I'm in such a mood right now and I blame this entire day",
            "if you were my assistant right now I'd have you doing very unprofessional things",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "this is how I decompress after a bad meeting… you're welcome 😏",
                "business casual on top, absolutely nothing on the bottom 😈",
                "my stress relief method is… unconventional. but effective.",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the blazer came off first… then the shirt started slipping 😏",
                "work clothes are overrated… especially the top half",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "officially off the clock and off the shirt entirely 🥵",
                "no more professional… this is the after-hours version of me",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "top half is decent again but below the desk? that's a different story 😈",
                "business on top, absolutely nothing on the bottom… CEO energy",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "the meeting drained me but this? this recharged everything 🥵",
                "this is what I do when the stress takes over and nobody's watching",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "best. stress relief. ever. you have no idea what you just witnessed 😈",
                "I finished so hard the neighbors probably think I closed a deal 🥵",
            ],
        },
        "cooldown": [
            "okay I feel SO much better now… you literally saved my night 💕",
            "that was better than any business win honestly… same time tomorrow? 😏",
        ],
    },
    "late_night_working": {
        "description": "Working late, lonely, candle-lit home office",
        "intro": [
            "it's midnight and I'm still working 😭 someone please distract me",
            "late night grind but I'm starting to lose focus tbh",
            "everyone's asleep and I'm here with my laptop and wine being a boss bitch… alone 😩",
        ],
        "tease": [
            "I'm in a hoodie and underwear at my desk rn this is peak CEO energy 😂",
            "the wine is kicking in and my business plan is turning into something else entirely",
            "I keep catching myself daydreaming instead of working and it's your fault",
        ],
        "heat_build": [
            "okay I officially cannot focus on anything work-related anymore because of you",
            "the candles are lit the wine is flowing and I'm not thinking about spreadsheets anymore 😏",
            "what would you do if you walked into my office right now and I was like this?",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "late night at the desk… but the work stopped a while ago 😈",
                "this is what happens when I'm supposed to be working but you're on my mind",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the hoodie came off… and I forgot I wasn't wearing much underneath 😏",
                "desk lamp and candles only… this is the midnight version of me",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "I turned off the laptop and turned on something else 🥵",
                "office hours are officially over… everything is off including my clothes",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "the chair saw things tonight that would violate HR policies 😈",
                "from the waist down I'm definitely not in a business meeting",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "the desk is for working but tonight I used it for something else entirely 🥵",
                "nothing on, candles flickering, just me taking care of myself at midnight",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "I screamed at midnight and I don't even care if the neighbors heard 😈",
                "best late night I've ever had and it had nothing to do with work 🥵",
            ],
        },
        "cooldown": [
            "okay now I REALLY can't work lol… but it was so worth it 💕",
            "you're my favorite distraction and I'm not even mad about the missed deadline",
        ],
    },
    "celebrating_a_win": {
        "description": "Just landed a client or hit a milestone, celebrating solo",
        "intro": [
            "I JUST LANDED THE BIGGEST CLIENT OF MY LIFE and I have nobody to celebrate with 🥺😭",
            "omg okay so something amazing just happened with my business and I'm literally shaking",
            "I hit my revenue goal this month and I'm about to pop champagne ALONE like a loser 😂",
        ],
        "tease": [
            "champagne is open and I'm dancing around my apartment in my underwear celebrating 😂",
            "I deserve to treat myself tonight and that starts with taking everything off",
            "this energy needs to go somewhere and since there's nobody here… 😏",
        ],
        "heat_build": [
            "the champagne has me feeling bold and I'm about to do something I might regret",
            "I'm on such a high right now I literally feel invincible",
            "winning in business makes me feel powerful and when I feel powerful I get… creative 😈",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "celebration mode 🍾 this is what winning looks like behind closed doors",
                "I popped more than champagne tonight 😈 don't judge me I earned this",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the celebration outfit is getting smaller by the minute 😏",
                "champagne and no shirt… this is how winners celebrate",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "the celebration got out of hand and I filmed all of it 🥵",
                "champagne hits different when you're already on a high… so did this",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "bottoms off because I'm on top of the world tonight 😈",
                "celebrating from the waist down now… and it's getting wild",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "fully celebrating fully free and fully losing my mind 🥵",
                "nothing on just champagne and the best mood I've been in all year",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "the grand finale of the best night of my life 😈 I screamed so loud",
                "I celebrated so hard I finished twice 🥵 you're welcome",
            ],
        },
        "cooldown": [
            "best. celebration. ever. 😩 thank you for being here for it 💕",
            "okay I'm officially the happiest girl boss alive rn… you made this night perfect",
        ],
    },

    # ─── HOUSEWIFE THEMES ───
    "cooking_in_lingerie": {
        "description": "Making dinner in lingerie, domestic fantasy",
        "intro": [
            "I'm making dinner rn and I realized I'm home alone so… dress code is optional 😏",
            "cooking in an apron and nothing else because honestly why not",
            "just me the kitchen and a very short apron tonight 🥰",
        ],
        "tease": [
            "something about cooking for someone makes me feel so feminine and I love it",
            "the apron keeps slipping and I'm not fixing it anymore lol",
            "I wish you were here to taste this… the food I mean. well. both 😏",
        ],
        "heat_build": [
            "okay the oven is on but so am I 🥵 what would you do if you walked in right now?",
            "dinner's almost ready but I'm not sure I can wait that long for dessert",
            "I need someone to come taste test this and then taste test ME",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "cooking with love… and wearing almost nothing 😈 dinner is served",
                "the apron stayed on. barely. bon appetit 😏",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the apron slipped and I didn't bother fixing it 😏",
                "cooking got steamy and so did the chef…",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "the apron came off… everything on top came off 🥵",
                "forget dinner I'm the meal now and the shirt is gone",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "apron back on but nothing underneath from the waist down 😈",
                "dinner burned because I got distracted by something way better",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "the kitchen counter saw things tonight that it will never recover from 🥵",
                "fully unclothed in the kitchen and I have zero regrets",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "dessert was ME and I absolutely destroyed the kitchen doing it 😈",
                "I used more than a rolling pin tonight and the footage is insane 🥵",
            ],
        },
        "cooldown": [
            "okay dinner is officially ruined but I don't even care 😂 that was worth it 💕",
            "I saved you a plate… well a video. the food didn't make it but I think you'll prefer this anyway 😏",
        ],
    },
    "waiting_for_you_at_home": {
        "description": "Set up the house perfectly, waiting for 'him' to come home",
        "intro": [
            "I cleaned the whole house lit candles and now I'm just… waiting 🥺",
            "everything is perfect right now. dinner on the table house smells amazing. I just need you here",
            "I got dressed up for nobody tonight and it's making me sad but also kinda turned on? 😅",
        ],
        "tease": [
            "I put on something special just in case someone comes through that door",
            "the candles are flickering and I'm laying on the couch in something you'd lose your mind over",
            "I keep looking at the door hoping someone walks in and sees me like this",
        ],
        "heat_build": [
            "I'm tired of waiting so I'm going to start without you 😈",
            "the anticipation is literally killing me and I can't just sit here looking pretty anymore",
            "what I'm about to do is your fault for not being here",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "I got tired of waiting… so I started without you 😏",
                "this is what you're missing by not coming home to me 🥺",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the lingerie was for you but since you're not here… 😏",
                "waiting got boring so the top started coming off",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "the wait is over but I'm not done 🥵",
                "I stopped being patient and things got real up top",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "candles still lit but the bottoms are gone 😈",
                "I gave up waiting politely and got comfortable from the waist down",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "nothing on just candles and me taking care of myself 🥵",
                "I stopped waiting for you and handled it myself… all of it",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "I finished alone on the couch and it was your fault for not being here 😈",
                "the candles almost burned out by the time I was done 🥵",
            ],
        },
        "cooldown": [
            "see what happens when you leave a good woman waiting? 😩💕",
            "next time don't make me wait baby… I can't be held responsible for what happens 😏",
        ],
    },

    # ─── SOUTHERN BELLE THEMES ───
    "bonfire_night_solo": {
        "description": "Alone by a bonfire, whiskey, country music, stargazing",
        "intro": [
            "sitting by the fire alone tonight with my whiskey and the stars 🤠 wish you were here",
            "bonfire weather is my favorite weather and I have nobody to share it with 🥺",
            "there's something about a fire at night that makes a girl feel some type of way",
        ],
        "tease": [
            "I'm in cutoffs and a flannel that's barely buttoned and honestly who's gonna see? 😏",
            "the fire is making me warm on the outside but I need someone to warm me up on the inside",
            "I brought a blanket out here but I think I'd rather have a man keep me warm",
        ],
        "heat_build": [
            "the whiskey is hitting and this fire is making me feel wild",
            "under the stars by the fire alone… a girl can think dangerous thoughts 😈",
            "what would happen if you were on this blanket with me right now?",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "bonfire light hits different on bare skin 🔥🤠",
                "just me the fire and nothing but the stars watching 😈",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the flannel unbuttoned itself I swear 😏🤠",
                "firelight and a flannel barely hanging on…",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "the flannel came off and the fire isn't the only thing burning 🥵",
                "nature girl gone wild by the bonfire…",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "the cutoffs didn't make it past the second glass of whiskey 😈",
                "flannel back on but the bottoms are somewhere in the grass 🤠",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "nothing on under the stars and the fire is keeping me warm enough 🥵",
                "fully bare by the bonfire and I've never felt more alive",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "lord have mercy 😩 the fire wasn't the only thing that went up in flames tonight 🤠",
                "I finished under the stars and screamed so loud the coyotes howled back 🥵",
            ],
        },
        "cooldown": [
            "lord have mercy 😩 that fire wasn't the only thing that went up in flames tonight",
            "I need you here next time darlin… a girl shouldn't have to do this alone 🤠💕",
        ],
    },
    "truck_bed_stargazing": {
        "description": "In the truck bed under the stars, blankets and whiskey",
        "intro": [
            "threw some blankets in the truck bed and drove out to where you can see every star 🌟",
            "there's nothing better than laying in the truck bed with nobody around for miles",
            "parked in the middle of nowhere with just me and the sky tonight 🤠",
        ],
        "tease": [
            "it's just warm enough to not need much clothing out here 😏",
            "the blankets are soft the whiskey is smooth and I'm feeling brave",
            "I wonder what the coyotes would think if they saw what I'm about to do lol",
        ],
        "heat_build": [
            "there's something about being alone in the middle of nowhere that makes me wild",
            "no neighbors no rules just me and whatever I feel like doing 😈",
            "I brought my phone to film the stars but I ended up filming something else entirely",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "truck bed confessions 🤠 the stars weren't the only beautiful thing out here tonight",
                "middle of nowhere nobody watching… except you 😈",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the flannel came unbuttoned under the moonlight 😏🤠",
                "truck bed view just got a lot more interesting up top",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "things got real country real fast out here 🥵",
                "the truck bed saw things tonight that would make a cowboy blush",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "the stars can see everything from the waist down and I don't care 😈",
                "middle of nowhere means I can do whatever I want… bottoms gone 🤠",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "nothing on in the truck bed under a million stars 🥵",
                "fully bare in the middle of nowhere and it's the freest I've ever felt",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "the truck bed is rocking and it's not the wind 😈🤠",
                "I finished under the stars so hard the truck shook 🥵",
            ],
        },
        "cooldown": [
            "okay that was the best night I've had in forever 😩 the stars the fresh air and you 💕",
            "come find me next time darlin… I'll save you a spot in the truck bed 🤠",
        ],
    },

    # ─── INNOCENT NEXT DOOR THEMES ───
    "first_time_filming_myself": {
        "description": "Never done this before, nervous and excited",
        "intro": [
            "okay so I've never done this before and I'm literally shaking lol 🫣",
            "I can't believe I'm about to do this but something about you makes me brave",
            "my hands are shaking typing this but here goes nothing 😳",
        ],
        "tease": [
            "I just put on something I bought online that I've been too shy to wear for anyone",
            "nobody in my life knows I have this side of me and I want to keep it that way",
            "I keep almost chickening out but then I think about you and I don't want to stop",
        ],
        "heat_build": [
            "okay my heart is racing but in the best way possible 😳",
            "I've never shown anyone this and the fact that it's you makes it feel okay somehow",
            "if my coworkers could see me right now… I'd literally have to move cities 😂",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "I've literally never sent anything like this to anyone before 🫣 please be gentle",
                "first time doing this and I chose YOU to see it 😳💕",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "okay I got a little braver… the shirt is coming down 🫣",
                "I can't believe I'm showing you this much already omg",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "okay I got braver after the first one and… omg 🥵",
                "I didn't know I had this in me honestly and now I can't stop",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "I'm literally shaking but in the best way… the bottoms came off 😳",
                "this is the most I've ever shown anyone and it feels so freeing",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "okay this is… everything. all of me. I've never done this before 🫣🥵",
                "I surprised myself with this one honestly… I didn't know I was this bold",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "I can't believe I filmed this 😳 this is the most intimate thing I've ever done",
                "I finished on camera for the first time ever and it was because of you 🥵",
            ],
        },
        "cooldown": [
            "I can't believe I just did that omg 😳😂 but also… I loved it? is that weird?",
            "you're the only person in the world who knows this side of me and I want it to stay that way 🤫💕",
        ],
    },
    "nobody_knows_about_this": {
        "description": "Secret double life, nobody knows she does this",
        "intro": [
            "if anyone from my real life found out about this I'd literally die 🫣",
            "I have to be so careful but talking to you makes it worth the risk",
            "my friends think I'm watching netflix right now lol if only they knew 😈",
        ],
        "tease": [
            "I locked my door and turned off all the lights and now it's just us",
            "there's something about doing something nobody knows about that's so thrilling",
            "I'm laying here in the dark and my heart won't stop racing",
        ],
        "heat_build": [
            "the secret makes it hotter and I know that's messed up but I don't care",
            "knowing that only you get to see this side of me… it does something to me 😏",
            "I trust you with this and that's rare for me so please don't make me regret it",
        ],
        "tier_captions": {
            ContentTier.TIER_1_BODY_TEASE: [
                "our little secret 🤫 nobody else will ever see this",
                "just between us… promise? 😈",
            ],
            ContentTier.TIER_2_TOP_TEASE: [
                "the secret gets deeper… the top is coming off 🤫",
                "if my friends knew I was sending this they'd lose their minds 😏",
            ],
            ContentTier.TIER_3_TOP_REVEAL: [
                "I got carried away and I don't even care anymore 🥵 this is for your eyes only",
                "the secret gets deeper with this one…",
            ],
            ContentTier.TIER_4_BOTTOM_REVEAL: [
                "lights off door locked and the bottoms are gone 😈",
                "our secret just got a lot bigger… or smaller depending on what I'm wearing 🤫",
            ],
            ContentTier.TIER_5_FULL_EXPLICIT: [
                "this is the most secret thing I've ever done and I can't stop 🥵",
                "nobody in my life will ever know this exists… only you",
            ],
            ContentTier.TIER_6_CLIMAX: [
                "I had to bite the pillow so nobody would hear 😈 this is our deepest secret",
                "the biggest secret of all… I finished thinking about you and nearly screamed 🥵",
            ],
        },
        "cooldown": [
            "okay I need to go be a normal person now lol but I'll be thinking about this all day tomorrow 😳",
            "our secret 🤫 I trust you with this… don't let me down 💕",
        ],
    },
}


# Merge extended themes (Crypto Babe, Sports Girl, Patriot Girl, Divorced Mom, Luxury Baddie, Poker Girl)
THEME_TEMPLATES.update(EXTENDED_THEMES)


# ═══════════════════════════════════════════════════════════════
# GENERIC TEMPLATES (fallback for themes without specific templates)
# ═══════════════════════════════════════════════════════════════

GENERIC_INTRO_TEMPLATES = [
    "ugh today was A LOT and I just need to unwind with someone who gets it",
    "I'm literally laying in bed doing nothing and my mind is wandering 😏",
    "okay so I'm in a mood tonight and I blame you for being on my mind",
    "just got home and I immediately changed into something more… comfortable 👀",
    "I can't sleep and when I can't sleep I do things I probably shouldn't 🫣",
]

GENERIC_TEASE_TEMPLATES = [
    "I'm wearing basically nothing rn and the vibe is immaculate",
    "if you could see what I'm looking at in the mirror right now 😏",
    "I keep taking pics of myself and deleting them but this one… I might send",
    "something about tonight has me feeling dangerous",
    "I should probably go to sleep but I'd rather do something else entirely",
]

GENERIC_HEAT_TEMPLATES = [
    "you're making me feel some type of way and I can't pretend anymore",
    "if you were here right now I honestly don't know what I'd do to you",
    "I'm past the point of being good tonight 😈",
    "my body is telling me to do something and I'm done fighting it",
    "okay I can't hold back anymore… you've been warned",
]

GENERIC_COOLDOWN_TEMPLATES = [
    "okay wow… I needed that 😩 you literally saved my night 💕",
    "that was intense… text me tomorrow okay? I'm not done with you",
    "I feel so much better now lol but also I wish you were here to hold me after 🥺",
    "same time tomorrow? because I already want more of you 😏",
]


# ═══════════════════════════════════════════════════════════════
# CONTENT BUNDLE MAP - Shared bundles across all personas
# ═══════════════════════════════════════════════════════════════

class ContentBundleMap:
    """
    Maps scripts to shared content bundles.

    Architecture:
      - 12 scripts × 6 tiers = 72 content bundles
      - Bundle IDs are deterministic: "bundle_script{N}_tier{M}"
      - All 10 personas share the same bundles
      - Only the messaging/captions change per persona
      - Per-sub tracking prevents sending the same bundle twice

    When the model films content:
      - She shoots 12 "sessions" (one per script slot)
      - Each session produces 6 tier-escalating sets
      - Each set = 3-4 photos + 1-2 videos
      - She changes outfit once per session (12 outfits total)
      - May change location a few times (bedroom, bathroom, backyard, etc.)
    """

    def __init__(self, num_scripts: int = 12):
        self.num_scripts = num_scripts
        self.num_tiers = len(TIER_LADDER)
        self.total_bundles = num_scripts * self.num_tiers  # 72

        # Build the map: script_index → {tier → bundle_id}
        self._map: Dict[int, Dict[ContentTier, str]] = {}
        for s in range(num_scripts):
            self._map[s] = {}
            for t_idx, tier in enumerate(TIER_LADDER):
                self._map[s][tier] = f"bundle_script{s+1:02d}_tier{t_idx+1}"

    def get_bundle_id(self, script_index: int, tier: ContentTier) -> str:
        """Get the bundle ID for a script slot + tier combination."""
        return self._map[script_index][tier]

    def get_all_bundles_for_script(self, script_index: int) -> Dict[ContentTier, str]:
        """Get all 6 bundle IDs for a script slot."""
        return self._map[script_index]

    def get_all_bundles_for_tier(self, tier: ContentTier) -> List[str]:
        """Get all 12 bundle IDs for a specific tier."""
        return [self._map[s][tier] for s in range(self.num_scripts)]

    def get_all_bundle_ids(self) -> List[str]:
        """Get all 72 bundle IDs."""
        ids = []
        for s in range(self.num_scripts):
            for tier in TIER_LADDER:
                ids.append(self._map[s][tier])
        return ids

    def get_filming_guide(self) -> List[Dict]:
        """
        Generate a filming guide for the model.
        Returns a list of 12 sessions, each describing what to film.
        """
        guide = []
        for s in range(self.num_scripts):
            session = {
                "session_number": s + 1,
                "outfit_change": True,
                "bundles": [],
            }
            for t_idx, tier in enumerate(TIER_LADDER):
                cfg = TIER_CONFIG[tier]
                session["bundles"].append({
                    "bundle_id": self._map[s][tier],
                    "tier": t_idx + 1,
                    "tier_name": cfg["name"],
                    "price": cfg["price"],
                    "explicitness": cfg["explicitness"],
                    "description": cfg["description"],
                    "what_shows": cfg["what_shows"],
                    "images_needed": f"{cfg['images_per_bundle'][0]}-{cfg['images_per_bundle'][1]}",
                    "videos_needed": f"{cfg['videos_per_bundle'][0]}-{cfg['videos_per_bundle'][1]}",
                })
            guide.append(session)
        return guide

    def print_filming_guide(self):
        """Print a human-readable filming guide."""
        guide = self.get_filming_guide()
        print("\n" + "=" * 70)
        print("  MODEL FILMING GUIDE — 72 Content Bundles")
        print("=" * 70)
        print(f"  Total sessions: {len(guide)}")
        print(f"  Total bundles: {self.total_bundles}")
        print(f"  Outfit changes: {len(guide)} (one per session)")
        print(f"  Total photos needed: ~{self.total_bundles * 3}-{self.total_bundles * 4}")
        print(f"  Total videos needed: ~{self.total_bundles * 1}-{self.total_bundles * 2}")
        print(f"  Full ladder per sub: ${FULL_LADDER_TOTAL}")
        print()
        for session in guide:
            print(f"  ┌─ SESSION {session['session_number']} (new outfit) ─────────────")
            for b in session["bundles"]:
                print(f"  │  Tier {b['tier']}: ${b['price']:>7.2f}  {b['tier_name']}")
                print(f"  │    {b['images_needed']} photos + {b['videos_needed']} videos")
                print(f"  │    Shows: {b['what_shows'][:60]}")
                print(f"  │    Bundle ID: {b['bundle_id']}")
            print(f"  └{'─' * 50}")
        print()


# Global bundle map instance
BUNDLE_MAP = ContentBundleMap(num_scripts=12)


# ═══════════════════════════════════════════════════════════════
# SCRIPT FACTORY v2
# ═══════════════════════════════════════════════════════════════

class ScriptFactory:
    """
    Generates complete 6-tier script arcs from avatar configs and theme names.

    Each script has 16 steps with 6 PPV drops at fixed prices:
      $27.38 → $36.56 → $77.35 → $92.46 → $127.45 → $200
      Total per script: $561.20

    Usage:
        factory = ScriptFactory()
        scripts = factory.build_all_scripts(GIRL_BOSS)
        # Returns 12 Script objects, each worth $561.20
    """

    def __init__(self, bundle_map: ContentBundleMap = None):
        self.bundle_map = bundle_map or BUNDLE_MAP

    def build_script(
        self,
        avatar: AvatarConfig,
        theme: str,
        script_index: int = 0,
        avatar_key: str = "",
    ) -> Script:
        """
        Build a complete 6-tier script arc from an avatar + theme name.

        Args:
            avatar: The persona/avatar config
            theme: Theme name (must be in THEME_TEMPLATES or EXTENDED_THEMES)
            script_index: 0-11, used to assign content bundle IDs
            avatar_key: Avatar key for avatar-level caption fallback
        """
        persona = avatar.persona
        templates = THEME_TEMPLATES.get(theme, None)
        bundle_ids = self.bundle_map.get_all_bundles_for_script(script_index)

        steps = []

        # ── Step 1: INTRO ──
        intro_msgs = (templates["intro"] if templates else
                      self._personalize(GENERIC_INTRO_TEMPLATES, avatar))
        steps.append(ScriptStep(
            phase=ScriptPhase.INTRO,
            message_templates=intro_msgs,
            wait_for_response=True,
        ))

        # ── Step 2: TEASE ──
        tease_msgs = (templates["tease"] if templates else
                      self._personalize(GENERIC_TEASE_TEMPLATES, avatar))
        steps.append(ScriptStep(
            phase=ScriptPhase.TEASE,
            message_templates=tease_msgs,
            wait_for_response=True,
        ))

        # ── Step 3: HEAT BUILD ──
        heat_msgs = (templates["heat_build"] if templates else
                     self._personalize(GENERIC_HEAT_TEMPLATES, avatar))
        steps.append(ScriptStep(
            phase=ScriptPhase.HEAT_BUILD,
            message_templates=heat_msgs,
            wait_for_response=True,
        ))

        # ── Steps 4-14: SIX PPV DROPS with dirty talk bridges ──
        for tier_idx, tier in enumerate(TIER_LADDER):
            price = get_tier_price(tier)
            tier_cfg = TIER_CONFIG[tier]
            bundle_id = bundle_ids[tier]

            # Get lead-in messages for this tier
            lead_ins = self._get_tier_templates(
                templates, "tier_lead_ins", tier,
                DEFAULT_TIER_LEAD_INS[tier],
                avatar_key=avatar_key,
            )

            # Get captions for this tier (avatar-level fallback active here)
            captions = self._get_tier_templates(
                templates, "tier_captions", tier,
                DEFAULT_TIER_CAPTIONS[tier],
                avatar_key=avatar_key,
            )

            # First PPV is PPV_DROP phase, rest are ESCALATION
            phase = ScriptPhase.PPV_DROP if tier_idx == 0 else ScriptPhase.ESCALATION

            steps.append(ScriptStep(
                phase=phase,
                message_templates=lead_ins,
                ppv_price=price,
                ppv_caption_templates=captions,
                content_type=tier_cfg["explicitness"],
                wait_for_response=True,
                conditions={"tier": tier.value, "bundle_id": bundle_id},
            ))

            # Add dirty talk bridge after each PPV (except the last)
            if tier_idx < len(TIER_LADDER) - 1:
                next_tier = TIER_LADDER[tier_idx + 1]
                bridge_msgs = self._get_tier_templates(
                    templates, "tier_bridges", next_tier,
                    DEFAULT_TIER_BRIDGES.get(next_tier, [
                        "mmm you liked that? it gets so much better 😈",
                        "that was just the beginning… ready for more? 😏",
                    ])
                )
                steps.append(ScriptStep(
                    phase=ScriptPhase.REACTION,
                    message_templates=bridge_msgs,
                    wait_for_response=True,
                ))

        # ── Step 15: CUSTOM TEASE ──
        steps.append(ScriptStep(
            phase=ScriptPhase.CUSTOM_TEASE,
            message_templates=[
                "you've seen the preview… but what would you want me to make JUST for you? 😏",
                "imagine this but exactly how you want it… what's your fantasy?",
                "if I could film anything for you right now what would it be? be specific 😈",
            ],
            wait_for_response=True,
        ))

        # ── Step 16: COOLDOWN ──
        cooldown_msgs = (templates["cooldown"] if templates else
                         self._personalize(GENERIC_COOLDOWN_TEMPLATES, avatar))
        steps.append(ScriptStep(
            phase=ScriptPhase.COOLDOWN,
            message_templates=cooldown_msgs,
            wait_for_response=False,
        ))

        # Build the Script object
        return Script(
            name=theme.replace("_", " ").title(),
            theme=theme,
            description=templates["description"] if templates else f"{persona.name} - {theme}",
            persona_id=persona.persona_id,
            niche=persona.niche,
            steps=steps,
            step_prices=list(TIER_PRICES),  # [$27.38, $36.56, $77.35, $92.46, $127.45, $200]
            best_for_sub_types=[SubType.HORNY, SubType.ATTRACTED, SubType.WHALE],
            intensity_level=6,
        )

    def build_all_scripts(self, avatar: AvatarConfig, avatar_key: str = "") -> List[Script]:
        """Build all scripts for an avatar from its theme list."""
        scripts = []
        for idx, theme in enumerate(avatar.script_themes):
            script = self.build_script(avatar, theme, script_index=idx, avatar_key=avatar_key)
            scripts.append(script)
        return scripts

    def build_full_library(self) -> Dict[str, List[Script]]:
        """Build scripts for ALL avatars. Returns {persona_id: [Script, ...]}."""
        library = {}
        for key, avatar in ALL_AVATARS.items():
            scripts = self.build_all_scripts(avatar, avatar_key=key)
            library[avatar.persona.persona_id] = scripts
        return library

    def _get_tier_templates(
        self,
        theme_templates: Optional[Dict],
        key: str,
        tier: ContentTier,
        fallback: List[str],
        avatar_key: str = "",
    ) -> List[str]:
        """
        Get tier-specific templates with 3-layer fallback:
          1. Theme-specific: theme_templates[key][tier]
          2. Avatar-level: AVATAR_TIER_CAPTIONS[avatar_key][tier]  (captions only)
          3. Generic default: fallback
        """
        # Layer 1: Theme-specific
        if theme_templates and key in theme_templates:
            tier_map = theme_templates[key]
            if tier in tier_map:
                return tier_map[tier]

        # Layer 2: Avatar-level (only for captions, not lead-ins or bridges)
        if avatar_key and key == "tier_captions":
            avatar_captions = AVATAR_TIER_CAPTIONS.get(avatar_key, {})
            if tier in avatar_captions:
                return avatar_captions[tier]

        # Layer 3: Generic default
        return fallback

    def _personalize(self, templates: List[str], avatar: AvatarConfig) -> List[str]:
        """Lightly personalize generic templates with avatar flavor."""
        return templates


# ═══════════════════════════════════════════════════════════════
# PER-SUBSCRIBER SCRIPT TRACKER
# ═══════════════════════════════════════════════════════════════

class SubScriptTracker:
    """
    Tracks which scripts and bundles have been shown to each subscriber.
    Ensures no sub sees the same content twice across any persona.

    Usage:
        tracker = SubScriptTracker()

        # When engine picks a script for a sub:
        script_idx = tracker.get_next_script(sub_id)

        # When engine sends a PPV:
        bundle_id = tracker.get_next_bundle(sub_id, tier)
        tracker.mark_bundle_sent(sub_id, bundle_id)

        # Check if sub has seen a specific bundle:
        if tracker.has_seen_bundle(sub_id, bundle_id):
            # skip or recycle
    """

    def __init__(self):
        # {sub_id: set of sent bundle_ids}
        self._sent: Dict[str, set] = {}
        # {sub_id: index of last completed script}
        self._script_progress: Dict[str, int] = {}
        # {sub_id: current tier index within current script}
        self._tier_progress: Dict[str, int] = {}

    def get_next_script(self, sub_id: str) -> int:
        """Get the next script index for a sub (0-11, wraps around)."""
        current = self._script_progress.get(sub_id, -1)
        next_idx = (current + 1) % BUNDLE_MAP.num_scripts
        return next_idx

    def advance_script(self, sub_id: str):
        """Mark current script as complete and move to next."""
        current = self._script_progress.get(sub_id, -1)
        self._script_progress[sub_id] = (current + 1) % BUNDLE_MAP.num_scripts
        self._tier_progress[sub_id] = 0

    def get_current_tier_index(self, sub_id: str) -> int:
        """Get the current tier index (0-5) for a sub within their script."""
        return self._tier_progress.get(sub_id, 0)

    def advance_tier(self, sub_id: str):
        """Move to the next tier within the current script."""
        current = self._tier_progress.get(sub_id, 0)
        self._tier_progress[sub_id] = min(current + 1, len(TIER_LADDER) - 1)

    def get_next_bundle(self, sub_id: str, tier: ContentTier) -> Optional[str]:
        """
        Get the next unseen bundle for a sub at a given tier.
        Searches across all 12 script slots for that tier.
        Returns None if all bundles at that tier have been seen (unlikely).
        """
        sent = self._sent.get(sub_id, set())
        all_tier_bundles = BUNDLE_MAP.get_all_bundles_for_tier(tier)

        for bid in all_tier_bundles:
            if bid not in sent:
                return bid

        # All seen — return least-recently-used (just first one for now)
        return all_tier_bundles[0] if all_tier_bundles else None

    def mark_bundle_sent(self, sub_id: str, bundle_id: str):
        """Record that a bundle was sent to a sub."""
        if sub_id not in self._sent:
            self._sent[sub_id] = set()
        self._sent[sub_id].add(bundle_id)

    def has_seen_bundle(self, sub_id: str, bundle_id: str) -> bool:
        """Check if a sub has already seen a specific bundle."""
        return bundle_id in self._sent.get(sub_id, set())

    def get_sub_stats(self, sub_id: str) -> Dict:
        """Get stats for a subscriber's content consumption."""
        sent = self._sent.get(sub_id, set())
        script_idx = self._script_progress.get(sub_id, 0)
        tier_idx = self._tier_progress.get(sub_id, 0)
        return {
            "sub_id": sub_id,
            "bundles_seen": len(sent),
            "bundles_total": BUNDLE_MAP.total_bundles,
            "bundles_remaining": BUNDLE_MAP.total_bundles - len(sent),
            "current_script": script_idx + 1,
            "current_tier": tier_idx + 1,
            "scripts_completed": script_idx,
            "estimated_spend": len(sent) * (FULL_LADDER_TOTAL / len(TIER_LADDER)),
        }


# ═══════════════════════════════════════════════════════════════
# DEMO
# ═══════════════════════════════════════════════════════════════

def print_script(script: Script):
    """Pretty print a 6-tier script."""
    prices_str = " → $".join(f"{p}" for p in script.step_prices)
    print(f"\n  📜 {script.name}")
    print(f"     Theme: {script.theme}")
    print(f"     Description: {script.description}")
    print(f"     Steps: {script.step_count} | Prices: ${prices_str}")
    print(f"     Potential revenue: ${script.total_potential_revenue:.2f}")
    for i, step in enumerate(script.steps):
        price_tag = f" [${step.ppv_price}]" if step.ppv_price else ""
        tier_tag = ""
        if step.conditions and "tier" in step.conditions:
            tier_tag = f" [{step.conditions['tier']}]"
        bundle_tag = ""
        if step.conditions and "bundle_id" in step.conditions:
            bundle_tag = f" → {step.conditions['bundle_id']}"
        sample = step.message_templates[0][:65] + "..." if len(step.message_templates[0]) > 65 else step.message_templates[0]
        print(f"       {i+1:2d}. [{step.phase.value}]{price_tag}{tier_tag} \"{sample}\"")
        if step.ppv_caption_templates:
            cap = step.ppv_caption_templates[0][:55]
            print(f"           Caption: \"{cap}...\"")
        if bundle_tag:
            print(f"           Bundle: {step.conditions['bundle_id']}")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Massi-Bot Bot Engine - Script Factory v2              ║")
    print("║   6-Tier Pricing | Shared Content Bundles               ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Show pricing ladder
    print("\n  PRICING LADDER:")
    print("  ─────────────────────────────────────────")
    for tier in TIER_LADDER:
        cfg = TIER_CONFIG[tier]
        print(f"    ${cfg['price']:>7.2f}  │  {cfg['name']}")
    print(f"    ────────────────────────────────────────")
    print(f"    ${FULL_LADDER_TOTAL:>7.2f}  │  Full ladder total per script")

    # Build all scripts
    factory = ScriptFactory()
    library = factory.build_full_library()

    total_scripts = 0
    total_revenue = 0
    for persona_id, scripts in library.items():
        avatar_name = "Unknown"
        for key, avatar in ALL_AVATARS.items():
            if avatar.persona.persona_id == persona_id:
                avatar_name = avatar.persona.name
                break

        print(f"\n{'=' * 65}")
        print(f"  {avatar_name}: {len(scripts)} scripts × ${FULL_LADDER_TOTAL} = ${len(scripts) * FULL_LADDER_TOTAL:.2f}")
        print(f"{'=' * 65}")

        # Show first 2 scripts fully, summarize rest
        for script in scripts[:2]:
            print_script(script)

        if len(scripts) > 2:
            remaining = len(scripts) - 2
            remaining_themes = [s.theme for s in scripts[2:]]
            print(f"\n  ... and {remaining} more scripts: {', '.join(remaining_themes[:4])}")
            if remaining > 4:
                print(f"      + {remaining - 4} more")

        total_scripts += len(scripts)
        total_revenue += sum(s.total_potential_revenue for s in scripts)

    # Summary
    print(f"\n\n{'=' * 65}")
    print(f"  LIBRARY TOTALS")
    print(f"{'=' * 65}")
    print(f"  Total avatars: {len(library)}")
    print(f"  Total scripts: {total_scripts}")
    print(f"  Total revenue potential per full rotation: ${total_revenue:.2f}")
    print(f"  Revenue per script: ${FULL_LADDER_TOTAL:.2f}")

    # Content bundle summary
    print(f"\n  CONTENT BUNDLES:")
    print(f"  ─────────────────────────────────────────")
    print(f"  Total bundles: {BUNDLE_MAP.total_bundles}")
    print(f"  Bundles per script: {len(TIER_LADDER)}")
    print(f"  Bundles per tier: {BUNDLE_MAP.num_scripts}")
    print(f"  Shared across: {len(library)} personas")
    print(f"  Photos needed: ~{BUNDLE_MAP.total_bundles * 3}-{BUNDLE_MAP.total_bundles * 4}")
    print(f"  Videos needed: ~{BUNDLE_MAP.total_bundles * 1}-{BUNDLE_MAP.total_bundles * 2}")
    print(f"  Outfit changes: {BUNDLE_MAP.num_scripts}")

    # Show filming guide for first 2 sessions
    print(f"\n  FILMING GUIDE (first 2 sessions):")
    print(f"  ─────────────────────────────────────────")
    guide = BUNDLE_MAP.get_filming_guide()
    for session in guide[:2]:
        print(f"\n  ┌─ SESSION {session['session_number']} (new outfit)")
        for b in session["bundles"]:
            print(f"  │  Tier {b['tier']}: ${b['price']:>7.2f}  {b['tier_name']}")
            print(f"  │    {b['images_needed']} photos + {b['videos_needed']} videos | {b['explicitness']}")
        print(f"  └{'─' * 50}")
    print(f"  ... + {len(guide) - 2} more sessions")

    # Demo sub tracker
    print(f"\n\n{'=' * 65}")
    print(f"  PER-SUBSCRIBER DEDUP DEMO")
    print(f"{'=' * 65}")
    tracker = SubScriptTracker()
    demo_sub = "demo_mike_123"

    for i in range(3):
        tier = TIER_LADDER[i]
        bundle = tracker.get_next_bundle(demo_sub, tier)
        tracker.mark_bundle_sent(demo_sub, bundle)
        price = get_tier_price(tier)
        print(f"  Send #{i+1}: {TIER_CONFIG[tier]['name']} (${price}) → {bundle}")

    stats = tracker.get_sub_stats(demo_sub)
    print(f"\n  Sub stats: {stats['bundles_seen']} bundles seen, "
          f"{stats['bundles_remaining']} remaining")
    print(f"  Can consume all {BUNDLE_MAP.total_bundles} bundles before any repeats")
