"""
Massi-Bot Bot Engine - Time Awareness & Message Variability System

Two problems solved:
  1. TIME AWARENESS — Bot knows what time/day it is and picks contextually
     appropriate scripts and messages. No "just got off work" at midnight.
  2. MESSAGE VARIABILITY — Bot never sends the same exact message twice to
     the same sub. Builds unique messages from composable parts + variable
     injection + history-aware dedup.

USAGE:
    from smart_messaging import TimeAwareSelector, MessageComposer

    # Time-aware script selection
    selector = TimeAwareSelector()
    script = selector.pick_script(scripts, hour=22, weekday=True)

    # Unique message generation
    composer = MessageComposer()
    msg = composer.compose(
        templates=warmup_templates,
        sub=sub,
        hour=22,
        sent_history=sub.recent_messages,
    )
"""

from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
import random
import hashlib


# ═══════════════════════════════════════════════════════════════
# TIME WINDOWS — When each script theme makes sense
# ═══════════════════════════════════════════════════════════════

# Time periods (24h format)
MORNING = (6, 11)       # 6am - 11am
AFTERNOON = (11, 17)    # 11am - 5pm
EVENING = (17, 21)      # 5pm - 9pm
LATE_NIGHT = (21, 2)    # 9pm - 2am  (wraps midnight)
ANYTIME = (0, 24)       # Always valid

# Script theme → valid time windows + day types
# If a theme isn't listed here, it's valid ANYTIME
THEME_TIME_WINDOWS = {
    # ─── GIRL BOSS ───
    "stressed_after_meeting":     {"hours": [(11, 20)], "days": "weekday"},
    "late_night_working":         {"hours": [(20, 3)],  "days": "any"},
    "celebrating_a_win":          {"hours": [(14, 3)],  "days": "any"},
    "need_a_break_from_hustle":   {"hours": [(10, 22)], "days": "weekday"},
    "wine_after_long_day":        {"hours": [(17, 2)],  "days": "any"},
    "lonely_in_success":          {"hours": [(19, 3)],  "days": "any"},

    # ─── HOUSEWIFE ───
    "cooking_in_lingerie":        {"hours": [(16, 21)], "days": "any"},
    "waiting_for_you_at_home":    {"hours": [(17, 23)], "days": "any"},
    "cleaning_day_tease":         {"hours": [(9, 16)],  "days": "any"},
    "baking_got_messy":           {"hours": [(10, 20)], "days": "any"},
    "bubble_bath_after_chores":   {"hours": [(18, 1)],  "days": "any"},
    "apron_only":                 {"hours": [(11, 21)], "days": "any"},

    # ─── SOUTHERN BELLE ───
    "bonfire_night_solo":         {"hours": [(19, 3)],  "days": "any"},
    "truck_bed_stargazing":       {"hours": [(20, 4)],  "days": "any"},
    "skinny_dipping_at_lake":     {"hours": [(20, 3)],  "days": "weekend"},
    "after_mudding_shower":       {"hours": [(14, 22)], "days": "any"},
    "barn_photoshoot":            {"hours": [(10, 18)], "days": "any"},
    "whiskey_and_cutoffs":        {"hours": [(18, 3)],  "days": "any"},

    # ─── CRYPTO BABE ───
    "portfolio_green_celebration": {"hours": [(9, 2)],  "days": "weekday"},
    "red_day_need_distraction":   {"hours": [(9, 23)],  "days": "weekday"},
    "late_night_charting":        {"hours": [(21, 4)],  "days": "any"},
    "miami_penthouse_solo":       {"hours": [(19, 4)],  "days": "weekend"},
    "after_conference_hotel":     {"hours": [(18, 2)],  "days": "weekday"},
    "bet_on_me":                  {"hours": [(12, 2)],  "days": "any"},

    # ─── SPORTS GIRL ───
    "game_day_jersey_only":       {"hours": [(12, 1)],  "days": "any"},
    "lost_a_bet_tease":           {"hours": [(14, 2)],  "days": "any"},
    "halftime_show":              {"hours": [(13, 23)], "days": "any"},
    "after_party_celebration":    {"hours": [(20, 4)],  "days": "any"},
    "super_bowl_alone":           {"hours": [(16, 2)],  "days": "weekend"},
    "sports_bar_bathroom":        {"hours": [(18, 2)],  "days": "any"},

    # ─── INNOCENT NEXT DOOR ───
    "first_time_filming_myself":  {"hours": [(19, 3)],  "days": "any"},
    "nobody_knows_about_this":    {"hours": [(20, 3)],  "days": "any"},
    "after_work_secret":          {"hours": [(17, 1)],  "days": "weekday"},
    "shy_girl_tries_lingerie":    {"hours": [(19, 2)],  "days": "any"},
    "reading_in_bed_escalates":   {"hours": [(20, 3)],  "days": "any"},
    "bath_time_confession":       {"hours": [(19, 1)],  "days": "any"},

    # ─── PATRIOT GIRL ───
    "flag_bikini_fourth_of_july": {"hours": [(11, 3)],  "days": "any"},
    "shooting_range_adrenaline":  {"hours": [(10, 20)], "days": "any"},
    "camo_lingerie":              {"hours": [(19, 3)],  "days": "any"},
    "dog_tags_and_nothing_else":  {"hours": [(20, 3)],  "days": "any"},
    "base_housing_lonely":        {"hours": [(18, 2)],  "days": "any"},
    "homecoming_fantasy":         {"hours": [(10, 22)], "days": "any"},

    # ─── DIVORCED MOM ───
    "wine_night_self_discovery":  {"hours": [(19, 2)],  "days": "any"},
    "trying_on_old_clothes_glow_up": {"hours": [(14, 23)], "days": "any"},
    "first_lingerie_since_divorce": {"hours": [(19, 2)],  "days": "any"},
    "spa_day_self_care":          {"hours": [(10, 20)], "days": "any"},
    "dancing_alone_in_kitchen":   {"hours": [(18, 1)],  "days": "any"},
    "confidence_comeback":        {"hours": [(14, 2)],  "days": "any"},

    # ─── LUXURY BADDIE ───
    "hotel_suite_solo":           {"hours": [(19, 4)],  "days": "any"},
    "designer_lingerie_haul":     {"hours": [(12, 23)], "days": "any"},
    "champagne_bubble_bath":      {"hours": [(18, 2)],  "days": "any"},
    "yacht_day_bikini":           {"hours": [(10, 19)], "days": "weekend"},
    "penthouse_view_tease":       {"hours": [(19, 4)],  "days": "any"},
    "shopping_spree_reward":      {"hours": [(12, 22)], "days": "any"},

    # ─── POKER GIRL ───
    "vegas_hotel_room_solo":      {"hours": [(20, 5)],  "days": "any"},
    "poker_night_strip_tease":    {"hours": [(19, 4)],  "days": "any"},
    "won_big_celebration":        {"hours": [(14, 4)],  "days": "any"},
    "lost_a_bet_dare":            {"hours": [(18, 4)],  "days": "any"},
    "fight_night_adrenaline":     {"hours": [(19, 2)],  "days": "weekend"},
    "whiskey_and_cards":          {"hours": [(19, 3)],  "days": "any"},
}


# ═══════════════════════════════════════════════════════════════
# TIME-AWARE MESSAGE POOLS — Different vibes for different hours
# ═══════════════════════════════════════════════════════════════

# Warming messages segmented by time of day
WARMUP_BY_TIME = {
    "morning": [
        "I woke up thinking about you and I can't shake it 😏",
        "it's early but I'm already in a mood and it's your fault",
        "I'm still in bed and I don't want to get up unless you give me a reason",
        "coffee hasn't hit yet but talking to you is waking me up in other ways",
        "I slept in something very small last night and I haven't changed yet 👀",
        "morning thoughts hit different when someone's on your mind",
        "the sun is barely up and I'm already thinking about things I shouldn't be",
        "I had a dream about you and I'm not ready to talk about it yet 😏",
    ],
    "afternoon": [
        "I'm supposed to be productive right now but my mind keeps wandering 😏",
        "lunch break and I'm looking at my phone thinking about you instead of eating",
        "the afternoon slump is hitting but you're the only thing keeping me awake",
        "I changed into something more comfortable after running errands and now I'm feeling some type of way",
        "there's something about a slow afternoon that makes a girl feel restless",
        "I'm laying on the couch doing nothing and my imagination is working overtime",
        "the house is quiet and my thoughts are getting louder 👀",
        "I keep catching myself daydreaming about stuff I probably shouldn't be",
    ],
    "evening": [
        "just got done with everything for the day and now it's just me and you 😏",
        "I changed into something more comfortable and by comfortable I mean barely anything",
        "the vibe tonight is candles music and whatever happens next",
        "I'm winding down for the night but I don't want to wind down alone",
        "something about the evening makes me feel bold… should I be worried?",
        "I poured a glass of wine and now I'm laying here thinking about you",
        "the sunset is hitting and so is this mood 😏",
        "tonight feels like one of those nights where I do something I might not normally do",
    ],
    "late_night": [
        "I should be sleeping but talking to you is way more fun 😏",
        "it's late and my mind is wandering to places it probably shouldn't",
        "can't sleep and when I can't sleep I do things I probably shouldn't 🫣",
        "the whole house is quiet and it's just us right now",
        "late night thoughts hit different and I blame you entirely",
        "I'm in bed and I'm not tired and that's a dangerous combination",
        "everyone else is asleep but I'm wide awake thinking about you",
        "there's something about late nights that makes me feel reckless 😈",
    ],
}

# Escalation leads segmented by time
ESCALATION_LEADS_BY_TIME = {
    "morning": [
        "okay so I've been laying here thinking and I can't hold it back anymore 😏",
        "it's way too early for me to be feeling like this but here we are",
        "I was going to wait until tonight but I literally cannot anymore 🫣",
        "my morning just took a very unexpected turn and it's your fault",
    ],
    "afternoon": [
        "okay I need to be honest… I've been thinking about something all day and I can't hold it back 😏",
        "this afternoon is about to get a lot less boring if I have anything to say about it",
        "I've been building up to saying something and I think now is the time",
        "the afternoon quiet is making me brave… should I be scared of that?",
    ],
    "evening": [
        "okay the wine is talking but honestly I've been wanting to say this all day 😏",
        "the evening mood is hitting and I can't pretend I'm not feeling it anymore",
        "something about tonight feels different and I'm done fighting it 😈",
        "I keep almost saying something and then stopping but not this time",
    ],
    "late_night": [
        "okay it's late and I'm done pretending I'm not thinking about this 😏",
        "late night me is braver than daytime me and right now she's in charge 😈",
        "I can't sleep because of you and I'm about to do something about it",
        "the things I think about at this hour would make you lose your mind",
    ],
}

# Tension build segmented by time
TENSION_BY_TIME = {
    "morning": [
        "mmmm starting the day like this? you're trouble 😈",
        "this is not how I expected my morning to go but I'm not complaining",
        "if I sent you something right now to start your day… could you handle it? 👀",
    ],
    "afternoon": [
        "mmmm this afternoon just got interesting 😈",
        "be careful what you ask for in the middle of the day…",
        "if I sent you something right now while you're supposed to be busy… what would you do? 👀",
    ],
    "evening": [
        "mmmm the evening just got a lot more interesting 😈",
        "be careful what you ask for tonight…",
        "if I sent you something right now… what would you do with it? 👀",
    ],
    "late_night": [
        "mmmm at this hour? you're definitely trouble 😈",
        "be careful what you ask for this late at night…",
        "late night + you + what I'm about to send = you're not sleeping tonight 👀",
    ],
}


# ═══════════════════════════════════════════════════════════════
# COMPOSABLE MESSAGE PARTS — Build unique messages from pieces
# ═══════════════════════════════════════════════════════════════

# Openers — how the message starts (conversational variety)
OPENERS = {
    "casual": [
        "okay so ", "honestly ", "I'm not gonna lie ", "hmm ",
        "sooo ", "okay hear me out ", "wait ", "ugh ",
        "lowkey ", "ngl ", "um ", "soooo ",
    ],
    "excited": [
        "omg ", "wait wait wait ", "okay okay ", "yesss ",
        "ohhh ", "no way ", "stoppp ", "ahhh ",
    ],
    "flirty": [
        "mmm ", "you know what ", "so I was thinking… ",
        "don't judge me but ", "between us… ", "can I be honest? ",
    ],
    "vulnerable": [
        "okay this is embarrassing but ", "I probably shouldn't say this but ",
        "don't laugh but ", "this is gonna sound crazy but ",
        "I've been going back and forth about saying this but ",
    ],
}

# Closers — how the message ends (adds natural trailing feel)
CLOSERS = {
    "teasing": [
        " 😏", " 👀", " 😈", " just saying", " lol",
        " don't @ me", " you've been warned",
    ],
    "sweet": [
        " 💕", " 🥰", " honestly", " for real",
        " and I mean that", " you're different",
    ],
    "playful": [
        " lol", " 😂", " oops", " my bad",
        " but also not sorry", " deal with it",
    ],
    "intense": [
        " 🥵", " and I'm not sorry", " no regrets",
        " I said what I said", " try me",
    ],
}

# Variable tokens the composer can inject
# {time_greeting} — "morning" / "afternoon" / "tonight" / etc.
# {sub_name} — subscriber's display name or username
# {callback} — a reference from sub's callback_references
# {day_context} — "this Monday" / "this weekend" / "tonight"


# ═══════════════════════════════════════════════════════════════
# TIME-AWARE SELECTOR
# ═══════════════════════════════════════════════════════════════

class TimeAwareSelector:
    """
    Selects scripts and messages appropriate for the current time/day.

    Usage:
        selector = TimeAwareSelector()

        # Filter scripts for current time
        valid = selector.filter_scripts_by_time(scripts, hour=22, is_weekend=True)

        # Get time-appropriate warming messages
        warmup = selector.get_warmup_messages(hour=22)
    """

    @staticmethod
    def get_time_period(hour: int) -> str:
        """Classify hour into a time period."""
        if 6 <= hour < 11:
            return "morning"
        elif 11 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "late_night"

    @staticmethod
    def get_time_greeting(hour: int) -> str:
        """Get a natural time reference for variable injection."""
        if 6 <= hour < 12:
            return random.choice(["this morning", "rn", "right now"])
        elif 12 <= hour < 17:
            return random.choice(["this afternoon", "rn", "right now"])
        elif 17 <= hour < 21:
            return random.choice(["tonight", "this evening", "rn"])
        else:
            return random.choice(["tonight", "right now", "at this hour"])

    @staticmethod
    def get_day_context(now: datetime = None) -> str:
        """Get a natural day reference."""
        now = now or datetime.now()
        day = now.strftime("%A")
        if now.weekday() >= 5:
            return random.choice([f"this {day}", "this weekend", "today"])
        return random.choice([f"this {day}", "today", "rn"])

    @staticmethod
    def is_time_valid(hour: int, is_weekend: bool, theme: str) -> bool:
        """Check if a theme is valid for the given time/day."""
        window = THEME_TIME_WINDOWS.get(theme)
        if not window:
            return True  # Not listed = valid anytime

        # Check day type
        day_rule = window.get("days", "any")
        if day_rule == "weekday" and is_weekend:
            return False
        if day_rule == "weekend" and not is_weekend:
            return False

        # Check time windows (supports midnight wraparound)
        for start, end in window.get("hours", [(0, 24)]):
            if start <= end:
                # Normal range: e.g., (9, 17)
                if start <= hour < end:
                    return True
            else:
                # Wraps midnight: e.g., (21, 3) means 21-24 + 0-3
                if hour >= start or hour < end:
                    return True

        return False

    def filter_scripts_by_time(
        self,
        scripts: list,
        hour: int = None,
        is_weekend: bool = None,
        now: datetime = None,
    ) -> list:
        """
        Filter a list of Script objects to only those valid right now.
        Always returns at least 1 script (falls back to full list if
        filtering would leave zero).
        """
        now = now or datetime.now()
        if hour is None:
            hour = now.hour
        if is_weekend is None:
            is_weekend = now.weekday() >= 5

        valid = [s for s in scripts if self.is_time_valid(hour, is_weekend, s.theme)]

        # Never return empty — fall back to full list
        return valid if valid else scripts

    def get_warmup_messages(self, hour: int = None) -> List[str]:
        """Get warming messages appropriate for the current time."""
        period = self.get_time_period(hour or datetime.now().hour)
        return WARMUP_BY_TIME.get(period, WARMUP_BY_TIME["evening"])

    def get_escalation_leads(self, hour: int = None) -> List[str]:
        """Get escalation lead-ins appropriate for the current time."""
        period = self.get_time_period(hour or datetime.now().hour)
        return ESCALATION_LEADS_BY_TIME.get(period, ESCALATION_LEADS_BY_TIME["evening"])

    def get_tension_messages(self, hour: int = None) -> List[str]:
        """Get tension build messages appropriate for the current time."""
        period = self.get_time_period(hour or datetime.now().hour)
        return TENSION_BY_TIME.get(period, TENSION_BY_TIME["evening"])


# ═══════════════════════════════════════════════════════════════
# MESSAGE COMPOSER — Never sends the same message twice
# ═══════════════════════════════════════════════════════════════

class MessageComposer:
    """
    Builds unique messages from composable parts with variable injection
    and history-aware deduplication.

    Three layers of variability:
      1. TEMPLATE SELECTION — Pick from time-appropriate pools
      2. COMPOSITING — Prepend random opener + append random closer
      3. VARIABLE INJECTION — Replace {tokens} with real context
      4. DEDUP — Check against sub's message history, re-roll if seen

    Usage:
        composer = MessageComposer()
        msg = composer.compose(
            templates=warmup_templates,
            sub=sub,
            hour=22,
        )
    """

    def __init__(self):
        # Track ALL messages sent to each sub for dedup
        # {sub_id: set of message hashes}
        self._sent_hashes: Dict[str, Set[str]] = {}

    @staticmethod
    def _hash_msg(msg: str) -> str:
        """Create a short hash of a message for dedup tracking."""
        # Normalize: lowercase, strip emojis/spaces for fuzzy match
        clean = ''.join(c for c in msg.lower() if c.isalnum() or c == ' ')
        clean = ' '.join(clean.split())  # collapse spaces
        return hashlib.md5(clean.encode()).hexdigest()[:12]

    def _is_duplicate(self, sub_id: str, msg: str) -> bool:
        """Check if this message (or something very similar) was already sent."""
        h = self._hash_msg(msg)
        return h in self._sent_hashes.get(sub_id, set())

    def _record_sent(self, sub_id: str, msg: str):
        """Record that a message was sent to a sub."""
        if sub_id not in self._sent_hashes:
            self._sent_hashes[sub_id] = set()
        self._sent_hashes[sub_id].add(self._hash_msg(msg))

    def compose(
        self,
        templates: List[str],
        sub=None,
        hour: int = None,
        add_opener: bool = False,
        add_closer: bool = False,
        opener_style: str = "casual",
        closer_style: str = "teasing",
        variables: Dict[str, str] = None,
        max_retries: int = 10,
    ) -> str:
        """
        Build a unique message from templates with optional compositing.

        Args:
            templates: Base message templates to pick from
            sub: Subscriber object (for dedup + variable injection)
            hour: Current hour (for time variables)
            add_opener: Prepend a random conversational opener
            add_closer: Append a random closer/emoji
            opener_style: "casual", "excited", "flirty", "vulnerable"
            closer_style: "teasing", "sweet", "playful", "intense"
            variables: Extra {key: value} pairs for injection
            max_retries: How many times to try before accepting a dupe
        """
        hour = hour if hour is not None else datetime.now().hour
        sub_id = sub.sub_id if sub else None
        vars_dict = variables or {}

        # Build time variables
        selector = TimeAwareSelector()
        vars_dict.setdefault("time_greeting", selector.get_time_greeting(hour))
        vars_dict.setdefault("day_context", selector.get_day_context())

        # Build sub variables
        if sub:
            name = sub.display_name or sub.username or ""
            vars_dict.setdefault("sub_name", name)

            if sub.callback_references:
                vars_dict.setdefault(
                    "callback",
                    random.choice(sub.callback_references[-5:])
                )

        # Try to build a unique message
        for attempt in range(max_retries):
            # Pick base template
            base = random.choice(templates)

            # Variable injection
            for key, val in vars_dict.items():
                base = base.replace(f"{{{key}}}", val)

            # Optional opener
            if add_opener and random.random() > 0.4:
                openers = OPENERS.get(opener_style, OPENERS["casual"])
                base = random.choice(openers) + base[0].lower() + base[1:]

            # Optional closer
            if add_closer and random.random() > 0.5:
                closers = CLOSERS.get(closer_style, CLOSERS["teasing"])
                # Don't add a closer if the message already ends with an emoji
                if not any(base.rstrip().endswith(e) for e in "😏😈🥵👀💕🥰😩😂🫣😳😤🤠"):
                    base += random.choice(closers)

            # Dedup check
            if sub_id and self._is_duplicate(sub_id, base):
                continue  # Try again

            # Record and return
            if sub_id:
                self._record_sent(sub_id, base)
            return base

        # Exhausted retries — return last attempt anyway
        if sub_id:
            self._record_sent(sub_id, base)
        return base

    def compose_from_time_pool(
        self,
        time_pools: Dict[str, List[str]],
        hour: int = None,
        sub=None,
        add_opener: bool = True,
        **kwargs,
    ) -> str:
        """
        Pick a time-appropriate template pool and compose from it.

        Args:
            time_pools: Dict of {time_period: [templates]}
                        e.g., WARMUP_BY_TIME, ESCALATION_LEADS_BY_TIME
            hour: Current hour
            sub: Subscriber for dedup
        """
        hour = hour if hour is not None else datetime.now().hour
        period = TimeAwareSelector.get_time_period(hour)
        templates = time_pools.get(period, time_pools.get("evening", []))
        return self.compose(templates, sub=sub, hour=hour, add_opener=add_opener, **kwargs)

    def get_stats(self, sub_id: str) -> Dict:
        """Get dedup stats for a subscriber."""
        sent = self._sent_hashes.get(sub_id, set())
        return {
            "unique_messages_sent": len(sent),
            "sub_id": sub_id,
        }


# ═══════════════════════════════════════════════════════════════
# DEMO
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔════════════════════════════════════════════════════════╗")
    print("║   Time Awareness & Message Variability System          ║")
    print("╚════════════════════════════════════════════════════════╝")

    selector = TimeAwareSelector()
    composer = MessageComposer()

    # ── Time period classification ──
    print("\n  TIME PERIOD CLASSIFICATION:")
    print("  ─────────────────────────────────────────")
    for hour in [7, 10, 13, 16, 19, 22, 1]:
        period = selector.get_time_period(hour)
        greeting = selector.get_time_greeting(hour)
        print(f"    {hour:2d}:00 → {period:<12} greeting: \"{greeting}\"")

    # ── Script time filtering ──
    print("\n\n  SCRIPT TIME FILTERING:")
    print("  ─────────────────────────────────────────")
    test_themes = [
        "stressed_after_meeting",
        "late_night_working",
        "bonfire_night_solo",
        "cooking_in_lingerie",
        "first_time_filming_myself",
    ]
    for hour in [9, 14, 20, 1]:
        valid = [t for t in test_themes if selector.is_time_valid(hour, False, t)]
        invalid = [t for t in test_themes if not selector.is_time_valid(hour, False, t)]
        print(f"\n    {hour:2d}:00 (weekday):")
        print(f"      ✅ Valid: {', '.join(valid) if valid else 'none'}")
        print(f"      ❌ Invalid: {', '.join(invalid) if invalid else 'none'}")

    # ── Message variability demo ──
    print("\n\n  MESSAGE VARIABILITY DEMO:")
    print("  ─────────────────────────────────────────")

    # Simulate sending 10 warmup messages to same sub
    from models import Subscriber
    demo_sub = Subscriber(username="demo_mike", sub_id="mike_123")
    demo_sub.callback_references = ["I run a marketing agency", "I'm from Dallas"]

    print(f"\n    10 warming messages for {demo_sub.username} at 10pm:")
    for i in range(10):
        msg = composer.compose_from_time_pool(
            WARMUP_BY_TIME,
            hour=22,
            sub=demo_sub,
            add_opener=True,
            opener_style="flirty",
        )
        print(f"      {i+1:2d}. \"{msg[:70]}{'...' if len(msg) > 70 else ''}\"")

    stats = composer.get_stats(demo_sub.sub_id)
    print(f"\n    Unique messages sent: {stats['unique_messages_sent']}")

    # Show variability across time periods
    print(f"\n    Same templates, different times:")
    for hour, label in [(8, "8am"), (14, "2pm"), (20, "8pm"), (23, "11pm")]:
        msg = composer.compose_from_time_pool(
            WARMUP_BY_TIME, hour=hour, add_opener=False,
        )
        print(f"      {label}: \"{msg[:65]}{'...' if len(msg) > 65 else ''}\"")

    # Escalation lead variety
    print(f"\n    Escalation leads by time of day:")
    for hour, label in [(9, "morning"), (14, "afternoon"), (20, "evening"), (23, "late night")]:
        msg = composer.compose_from_time_pool(
            ESCALATION_LEADS_BY_TIME, hour=hour, add_opener=False,
        )
        print(f"      {label}: \"{msg[:65]}{'...' if len(msg) > 65 else ''}\"")

    # ── Weekend filter demo ──
    print(f"\n\n  WEEKEND FILTER:")
    print("  ─────────────────────────────────────────")
    weekend_themes = ["skinny_dipping_at_lake", "yacht_day_bikini", "fight_night_adrenaline"]
    for theme in weekend_themes:
        weekday = selector.is_time_valid(22, False, theme)
        weekend = selector.is_time_valid(22, True, theme)
        print(f"    {theme}: weekday={'✅' if weekday else '❌'} weekend={'✅' if weekend else '❌'}")
