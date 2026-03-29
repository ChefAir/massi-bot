"""
Massi-Bot Bot Engine - Message Analyzer
Analyzes incoming subscriber messages to detect:
- Intent and emotional state
- Objections and resistance
- Whale signals
- Timewaster patterns
- Source IG account attribution (without asking directly)
- Qualifying information extraction
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from models import (
    SubType, SubState, SubTier, ObjectionType, Subscriber,
    Persona, NicheType
)


class MessageAnalyzer:
    """
    Analyzes subscriber messages and extracts actionable intelligence.
    This is the 'qualification brain' described across Docs 3, 5, and 6.
    """

    # ─────────────────────────────────────────
    # IG ATTRIBUTION DETECTION
    # ─────────────────────────────────────────

    # Niche-specific keyword maps for detecting which IG account they came from.
    # The bot uses contextual clues from the sub's first messages instead of
    # asking directly. (See Doc 2 + your multi-IG requirement)
    NICHE_SIGNAL_MAP = {
        NicheType.FITNESS: {
            "keywords": ["gym", "workout", "fit", "gains", "muscles", "abs",
                         "squat", "yoga", "protein", "lifting", "athletic",
                         "sweaty", "body", "lean", "toned", "exercise"],
            "topics": ["gym pic", "workout video", "fitness post", "gym selfie"],
        },
        NicheType.GAMER: {
            "keywords": ["game", "gaming", "stream", "twitch", "valorant",
                         "fortnite", "cod", "apex", "minecraft", "discord",
                         "controller", "headset", "pc", "console", "setup"],
            "topics": ["stream", "gaming clip", "gamer girl", "playing"],
        },
        NicheType.EGIRL: {
            "keywords": ["aesthetic", "anime", "cosplay", "uwu", "kawaii",
                         "egirl", "alt", "goth", "emo", "e-girl", "weeb",
                         "manga", "hentai", "catgirl", "pink hair"],
            "topics": ["cosplay", "anime post", "tiktok"],
        },
        NicheType.LATINA: {
            "keywords": ["mami", "papi", "chica", "bonita", "caliente",
                         "latina", "spanish", "reggaeton", "bachata",
                         "puerto rico", "colombia", "mexico", "dominican"],
            "topics": ["dancing", "latin", "spanish post"],
        },
        NicheType.MILF: {
            "keywords": ["mature", "experienced", "woman", "cougar", "milf",
                         "older", "sophisticated", "classy", "elegant",
                         "wine", "lingerie"],
            "topics": ["mature content", "real woman"],
        },
        NicheType.BADDIE: {
            "keywords": ["baddie", "slay", "queen", "boss", "luxe", "drip",
                         "vibe", "fire", "stunner", "baddest", "designer",
                         "nails", "glam"],
            "topics": ["baddie post", "glam pic", "outfit"],
        },
        NicheType.GIRL_NEXT_DOOR: {
            "keywords": ["cute", "sweet", "pretty", "smile", "eyes", "natural",
                         "wholesome", "genuine", "real", "beautiful", "lovely",
                         "adorable", "nice"],
            "topics": ["selfie", "cute pic", "photo"],
        },
    }

    @classmethod
    def detect_niche_from_message(
        cls,
        message: str,
        available_personas: List[Persona]
    ) -> Optional[str]:
        """
        Detect which IG account/persona the sub likely came from
        based on keywords in their messages.
        Returns persona_id if confident, None if ambiguous.
        """
        message_lower = message.lower()
        scores = {}

        for persona in available_personas:
            score = 0
            niche = persona.niche

            # Check against standard niche signals
            if niche in cls.NICHE_SIGNAL_MAP:
                signals = cls.NICHE_SIGNAL_MAP[niche]
                for kw in signals["keywords"]:
                    if kw in message_lower:
                        score += 2
                for topic in signals["topics"]:
                    if topic in message_lower:
                        score += 3

            # Check against persona-specific keywords
            for kw in persona.niche_keywords:
                if kw.lower() in message_lower:
                    score += 3

            # Check against persona-specific topics
            for topic in persona.niche_topics:
                if topic.lower() in message_lower:
                    score += 4

            # Check for specific IG handle mention
            if persona.ig_account_tag and persona.ig_account_tag.lower() in message_lower:
                score += 20  # Dead giveaway

            if score > 0:
                scores[persona.persona_id] = score

        if not scores:
            return None

        # Return highest scoring persona if score is high enough
        best = max(scores, key=scores.get)
        if scores[best] >= 4:  # Confidence threshold
            return best
        return None

    # ─────────────────────────────────────────
    # INTENT DETECTION
    # ─────────────────────────────────────────

    @staticmethod
    def detect_sexual_intent(message: str) -> float:
        """
        Score 0-1 for how sexually charged the message is.
        Used to determine if the sub is initiating sexual direction (Doc 4, Section 3).

        Three tiers:
          - Explicit (0.4-0.5): Direct sexual words
          - Suggestive (0.2-0.3): Implying sexual interest without explicit words
          - Flirtatious (0.1-0.15): Escalating interest, requesting content
        """
        message_lower = message.lower()
        # Normalize elongated words: fuuuck→fuck, mmmm→mm, sooo→so
        normalized = re.sub(r'(.)\1{2,}', r'\1\1', message_lower)

        sexual_signals = [
            # ── Explicit tier ──
            (r'\b(horny|turned on|aroused|erect|throb)', 0.4),
            (r'(dick|cock|cum|pussy|ass\b|tits|boobs|naked|nude)', 0.5),
            (r'\b(suck|ride|lick|spank|choke|moan|orgasm|climax)', 0.45),
            (r'(fuck|fuk|fck)', 0.4),  # catches fuuuck after normalization
            (r'(tongue|lips.{0,10}(clit|pussy|body)|legs.{0,5}shak)', 0.45),
            (r'(indulg|devour|smoth|face.{0,10}between)', 0.4),
            (r'(i want all of you|i need you.{0,5}(now|bad|so)|can.t resist)', 0.4),
            (r'(let.s have.{0,5}fun|i.m ready|vamos)', 0.35),

            # ── Suggestive tier ──
            (r'\b(hard|wet|touch|taste|swallow|strip|naughty)\b', 0.3),
            (r'\b(bed|shower|lingerie|panties|bra|underwear)\b', 0.2),
            (r'(want you|need you|fantasize|imagine|dream about)', 0.25),
            (r'(make me|drive me|you make me|driving me)', 0.2),
            (r'(what i.?d do|what would i do|if i was there|if i were there)', 0.3),
            (r'(come over|on top of|inside|behind you|bend)', 0.35),
            (r'(turn.{0,3} on|getting excited|can.t control)', 0.3),
            (r'(take it off|take.{0,5}off|clothes off|nothing on)', 0.3),

            # ── Requesting/wanting content tier ──
            (r'(show me|send me|let me see|i wanna see|need to see)', 0.25),
            (r'(send it|more of that|i need more|want more|give me more)', 0.25),
            (r'(pic|video|content|photo).{0,10}(send|show|see|want)', 0.2),

            # ── Emoji signals ──
            (r'🍆|🍑|💦|🥵|👅|🤤', 0.25),
            (r'😈', 0.15),
            (r'🔥', 0.1),

            # ── Flirtatious escalation ──
            (r'\b(sexy|hot|beautiful body|gorgeous body|insane body)\b', 0.15),
            (r'(can.t stop|can.t handle|can.t resist|can.t wait)', 0.15),
            (r'(you.re (killing|ruining|wrecking|destroying) me)', 0.2),
            (r'(i.m (done|finished|gone|dead|weak))', 0.15),
            (r'(please|beg|begging)', 0.1),
            (r'(tease|teasing|teas)', 0.15),
            (r'mm+', 0.1),  # catches mmm, mmmm etc after normalization
        ]
        score = 0.0
        for pattern, weight in sexual_signals:
            if re.search(pattern, normalized):
                score += weight
        return min(score, 1.0)

    @staticmethod
    def detect_emotional_openness(message: str) -> float:
        """
        Score 0-1 for emotional vulnerability/openness.
        High scores = GFE potential (Doc 5).
        """
        message_lower = message.lower()
        emotional_signals = [
            (r'\b(lonely|alone|single|miss|sad|depressed|bored)\b', 0.3),
            (r'\b(divorced|breakup|broke up|separated|ex |my ex)\b', 0.35),
            (r'\b(no one|nobody|don.t have anyone|by myself)\b', 0.3),
            (r'\b(connection|real|genuine|different|special)\b', 0.25),
            (r'\b(long day|rough day|tired|stressed|exhausted)\b', 0.2),
            (r'\b(you.re different|not like other|actually talk)\b', 0.4),
            (r'\b(open up|personal|deep|feelings|care about)\b', 0.25),
        ]
        score = 0.0
        for pattern, weight in emotional_signals:
            if re.search(pattern, message_lower):
                score += weight
        return min(score, 1.0)

    # ─────────────────────────────────────────
    # SUB TYPE CLASSIFICATION
    # ─────────────────────────────────────────

    @classmethod
    def classify_sub_type(cls, sub: Subscriber) -> SubType:
        """
        Classify subscriber type based on accumulated signals.
        From Doc 3, Section 2: Horny / Attracted / Curious / Timewaster.
        """
        # Already classified as whale by spending
        if sub.spending.tier == SubTier.WHALE:
            return SubType.WHALE

        # Check timewaster signals (Doc 3, Section 10)
        timewaster_score = 0
        if sub.asked_for_free_content >= 2:
            timewaster_score += 3
        if sub.one_word_reply_streak >= 4:
            timewaster_score += 2
        if sub.asked_for_meetup:
            timewaster_score += 2
        if sub.message_count > 15 and not sub.spending.is_buyer:
            timewaster_score += 2
        if timewaster_score >= 4:
            return SubType.TIMEWASTER

        # Analyze recent messages for classification
        recent_text = " ".join(
            m["content"] for m in sub.recent_messages[-10:]
            if m["role"] == "sub"
        )

        sexual_score = cls.detect_sexual_intent(recent_text)
        emotional_score = cls.detect_emotional_openness(recent_text)

        # Horny: high sexual intent early
        if sexual_score >= 0.4:
            return SubType.HORNY

        # Curious: mentions non-sexual topics, interests
        curious_signals = ["tiktok", "reddit", "instagram", "post", "video",
                          "game", "anime", "movie", "show", "music", "content"]
        if any(s in recent_text.lower() for s in curious_signals) and sexual_score < 0.2:
            return SubType.CURIOUS

        # Attracted: compliments, engagement, but not overtly sexual
        attracted_signals = ["beautiful", "gorgeous", "pretty", "cute", "amazing",
                           "love your", "obsessed", "fan", "followed you"]
        if any(s in recent_text.lower() for s in attracted_signals):
            return SubType.ATTRACTED

        # If emotional openness is high, lean toward attracted (GFE potential)
        if emotional_score >= 0.3:
            return SubType.ATTRACTED

        return SubType.UNKNOWN

    # ─────────────────────────────────────────
    # OBJECTION DETECTION
    # ─────────────────────────────────────────

    @staticmethod
    def detect_objection(message: str) -> Optional[ObjectionType]:
        """Detect if a message contains a price/buying objection (Doc 6)."""
        msg = message.lower()

        # "Too expensive" patterns
        if any(p in msg for p in ["too expensive", "too much", "that's a lot",
                                   "can't afford", "steep", "pricey", "costly"]):
            return ObjectionType.TOO_EXPENSIVE

        # "Can I get it cheaper" patterns
        if any(p in msg for p in ["cheaper", "discount", "deal", "lower",
                                   "can i get it for", "how about $", "do it for"]):
            return ObjectionType.WANTS_CHEAPER

        # "Maybe later" patterns
        if any(p in msg for p in ["maybe later", "not right now", "another time",
                                   "not today", "later", "idk maybe", "think about it"]):
            return ObjectionType.MAYBE_LATER

        # "Spent too much" patterns
        if any(p in msg for p in ["spent too much", "already spent", "over budget",
                                   "broke", "can't spend more", "wallet"]):
            return ObjectionType.SPENT_TOO_MUCH

        # "Free content" patterns
        if any(p in msg for p in ["free", "can i see", "just send", "preview",
                                   "sample", "just one", "show me first"]):
            return ObjectionType.WANTS_FREE

        # "Meetup" patterns
        if any(p in msg for p in ["meet up", "meetup", "meet in person",
                                   "where do you live", "come over", "visit",
                                   "hang out", "real life", "in person"]):
            return ObjectionType.WANTS_MEETUP

        return None

    # ─────────────────────────────────────────
    # QUALIFYING DATA EXTRACTION
    # ─────────────────────────────────────────

    @staticmethod
    def extract_age(message: str) -> Optional[int]:
        """Extract age from message."""
        patterns = [
            r"i'?m (\d{2})",
            r"i am (\d{2})",
            r"(\d{2}) years? old",
            r"^(\d{2})$",
            r"age:? ?(\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                age = int(match.group(1))
                if 18 <= age <= 80:
                    return age
        return None

    @staticmethod
    def extract_location(message: str) -> Optional[str]:
        """Extract location from message."""
        msg_lower = message.lower()

        # Try explicit "from X" or "in X" patterns first
        from_patterns = [
            r"(?:from|based in|located in|live in|living in)\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\.|!|\?|,|$|\s+and\s|\s+work)",
        ]
        for pattern in from_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                candidate = match.group(1).strip()
                # Reject if it's clearly not a location
                non_locations = ["single", "married", "divorced", "tired", "here",
                                "good", "fine", "okay", "great", "home"]
                if candidate.lower() not in non_locations and len(candidate) > 1:
                    return candidate.title()

        # Fallback: check for known locations using word boundaries
        locations = {
            "new york": "New York", "los angeles": "Los Angeles",
            "chicago": "Chicago", "houston": "Houston", "phoenix": "Phoenix",
            "philadelphia": "Philadelphia", "san antonio": "San Antonio",
            "san diego": "San Diego", "dallas": "Dallas", "austin": "Austin",
            "miami": "Miami", "atlanta": "Atlanta", "denver": "Denver",
            "seattle": "Seattle", "boston": "Boston", "detroit": "Detroit",
            "nashville": "Nashville", "portland": "Portland", "las vegas": "Las Vegas",
            "oklahoma": "Oklahoma", "cleveland": "Cleveland", "tampa": "Tampa",
            "california": "California", "texas": "Texas", "florida": "Florida",
            "ohio": "Ohio", "georgia": "Georgia", "michigan": "Michigan",
            "tennessee": "Tennessee", "virginia": "Virginia", "colorado": "Colorado",
            "london": "London", "toronto": "Toronto", "sydney": "Sydney",
        }
        for loc_lower, loc_proper in locations.items():
            # Use word boundary to prevent "la" matching inside "dallas"
            if re.search(r'\b' + re.escape(loc_lower) + r'\b', msg_lower):
                return loc_proper

        return None

    @staticmethod
    def extract_occupation(message: str) -> Optional[str]:
        """Extract job/occupation from message."""
        msg_lower = message.lower()

        # Direct extraction patterns - most reliable
        direct_patterns = [
            r"(?:i work in|i work as|i'm a|i am a|i'm an|i am an)\s+([\w\s]{3,30}?)(?:\.|!|\?|,|$| and )",
            r"(?:i do|i run|i own|i manage)\s+(?:a\s+)?([\w\s]{3,30}?)(?:\.|!|\?|,|$)",
            r"work (?:in|at|for)\s+([\w\s]{3,30}?)(?:\.|!|\?|,|$)",
        ]

        # Job title keywords to validate matches
        job_keywords = [
            "engineer", "developer", "doctor", "nurse", "teacher", "lawyer",
            "accountant", "manager", "director", "consultant", "analyst",
            "designer", "sales", "marketing", "finance", "construction",
            "mechanic", "electrician", "plumber", "military", "police",
            "firefighter", "chef", "pilot", "driver", "owner", "ceo",
            "programmer", "software", "tech", "banker", "trader",
            "oil", "gas", "agency", "contractor", "business", "real estate",
            "executive", "officer", "supervisor", "foreman", "welder",
            "trucker", "lineman", "surgeon", "dentist", "therapist",
        ]

        # First try: direct pattern extraction
        for pattern in direct_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                job = match.group(1).strip()
                # Validate it looks like a job (not random words)
                if any(kw in job for kw in job_keywords) and len(job) > 2:
                    return job.title()

        # Second try: keyword detection without full pattern match
        for keyword in job_keywords:
            # Use word boundary to prevent false matches like "it " in "with"
            if re.search(r'\b' + re.escape(keyword) + r'\b', msg_lower):
                # Skip if the keyword is part of a non-job context
                if keyword == "tech" and "technology" not in msg_lower:
                    return "Tech"
                if keyword in ["oil", "gas"]:
                    return "Oil & Gas"
                if keyword == "agency":
                    return "Agency"
                return keyword.title()

        return None

    @staticmethod
    def detect_relationship_status(message: str) -> Optional[str]:
        """Detect relationship status from message."""
        msg = message.lower()
        if any(w in msg for w in ["single", "not seeing anyone", "nobody",
                                   "no girlfriend", "no one"]):
            return "single"
        if any(w in msg for w in ["divorced", "divorce"]):
            return "divorced"
        if any(w in msg for w in ["separated", "split"]):
            return "separated"
        if any(w in msg for w in ["married", "wife", "husband"]):
            return "married"
        if any(w in msg for w in ["girlfriend", "bf", "boyfriend", "partner",
                                   "relationship", "taken"]):
            return "in_relationship"
        return None

    # ─────────────────────────────────────────
    # ENGAGEMENT QUALITY SIGNALS
    # ─────────────────────────────────────────

    @staticmethod
    def assess_message_quality(message: str) -> Dict[str, Any]:
        """Assess overall message quality for engagement scoring."""
        words = message.split()
        return {
            "word_count": len(words),
            "is_one_word": len(words) <= 1,
            "is_paragraph": len(words) >= 20,
            "has_question": "?" in message,
            "has_emoji": bool(re.search(r'[\U0001F300-\U0001F9FF]', message)),
            "enthusiasm_level": (
                "high" if any(c in message for c in ["!", "🔥", "😍", "❤️", "😈"])
                else "low" if len(words) <= 2
                else "medium"
            ),
            "sexual_score": MessageAnalyzer.detect_sexual_intent(message),
            "emotional_score": MessageAnalyzer.detect_emotional_openness(message),
        }

    # ─────────────────────────────────────────
    # WHALE SIGNAL DETECTION
    # ─────────────────────────────────────────

    @staticmethod
    def detect_affirmative(message: str) -> bool:
        """
        Return True if the message is a clear affirmative response to a yes/no question.
        Used in qualifying state to advance past a question even when data extraction fails.
        Examples: "yes", "I do", "yeah lol", "I actually do", "yep", "sure do", "I am"
        """
        msg = message.lower().strip()
        # Remove punctuation for matching
        import re as _re
        clean = _re.sub(r"[^\w\s]", "", msg)

        affirmative_patterns = [
            r"^(yes|yeah|yep|yup|yea|sure|definitely|absolutely|of course|for sure)\b",
            r"^i (do|am|have|did|run|own|work|yes)\b",
            r"\bi (actually|do|am|definitely|totally) (do|am|have|run|own|work)\b",
            r"^(correct|right|true|exactly|totally|100|facts)\b",
            r"^(lol yes|yes lol|yeah lol|lol yeah|haha yes|lmao yes)\b",
        ]
        for pat in affirmative_patterns:
            if _re.search(pat, clean):
                return True
        return False

    @staticmethod
    def detect_whale_signals(message: str) -> List[str]:
        """
        Detect whale indicator signals (from Doc 3, Section 9).
        Returns list of triggered signals.
        """
        msg = message.lower()
        signals = []

        # "You're different" = whale radar (Doc 3)
        if any(p in msg for p in ["you're different", "you seem different",
                                   "not like other", "something about you",
                                   "stood out", "special"]):
            signals.append("differentiation_signal")

        # Has OF experience
        if any(p in msg for p in ["subbed before", "other pages", "other girls",
                                   "first time chatting like this", "never talked like this"]):
            signals.append("experienced_buyer")

        # Emotional investment early
        if any(p in msg for p in ["i needed this", "you're making my day",
                                   "this is nice", "i love talking to you",
                                   "best conversation"]):
            signals.append("emotional_buy_in")

        # Money signals
        if any(p in msg for p in ["money isn't", "don't care about price",
                                   "whatever you want", "name your price",
                                   "i'll buy anything", "take my money"]):
            signals.append("money_no_object")

        # Paragraph responses (high effort = high investment)
        if len(msg.split()) >= 30:
            signals.append("high_effort_message")

        return signals
