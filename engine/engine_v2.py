"""
Massi-Bot Bot Engine v2 - Integrated Conversation Engine
Fully wired to: avatars, 6-tier pricing, script factory, content bundles.

This engine uses:
  - AvatarConfig for voice, qualifying questions, GFE touchpoints
  - 6-tier pricing ($27.38 → $200) with fixed non-negotiable prices
  - Script Factory v2 for tier-specific lead-ins, captions, and bundle IDs
  - SubScriptTracker for per-subscriber content deduplication
  - ContentCatalog for real content-aware PPV bundles (when available)
  - ModelProfile for accurate content descriptions
  - AttributionEngine for IG source detection

Script integration flow:
  1. Sub reaches FIRST_PPV_READY → engine assigns a script via SubScriptTracker
  2. Each PPV drop pulls lead-ins, captions, and bundle_id from the script's steps
  3. Dirty talk bridges between tiers come from the script's REACTION steps
  4. When all 6 tiers are sent → script marked complete, sub enters POST_SESSION
  5. When sub re-engages → next script assigned (12 total before any repeat)
"""

import re
import random
import logging
from typing import List, Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

_BUY_SIGNALS = re.compile(
    r"\b(i want (?:all of )?you|i need you|show me (?:more|everything)|i'm ready|"
    r"let'?s (?:have fun|do (?:it|this)|go)|vamos|"
    r"take (?:it|them) off|undress|strip|i want to see|let me see|"
    r"ready (?:for|to)|give (?:it to )?me|i need (?:to see|more)|"
    r"what are you waiting for|stop teasing|enough teasing|"
    r"i can'?t (?:wait|resist|hold back)|show me what you got)\b",
    re.IGNORECASE,
)

from models import (
    SubState, SubType, SubTier, ObjectionType,
    Subscriber, BotAction, Script, ScriptStep, ScriptPhase
)
from avatars import AvatarConfig, ALL_AVATARS
from session_control import (
    SessionController, EGO_OBJECTIONS, BROKEY_TREATMENT, BROKEY_DISMISSAL,
    SESSION_LOCK_DESIRE, SESSION_LOCK_BOUNDARY, SESSION_LOCK_FIRM,
    CUSTOM_DECLINED_GRACEFUL, GFE_FLIRTY_BANTER, GFE_SWEET_INTIMATE,
    GFE_PLAYFUL_TEASING, GFE_DESIRE_BUILDING, GFE_LATE_NIGHT,
    GFE_MORNING_AFTER, GFE_JEALOUSY_PLAY, BROKEY_COOLING_WARMTH,
)
from onboarding import (
    ModelProfile, ContentCatalog, ContentBundle,
    ContentTier, TIER_CONFIG, get_tier_price
)
from attribution import AttributionEngine
from analyzer import MessageAnalyzer
from script_factory import (
    ScriptFactory, SubScriptTracker, ContentBundleMap, BUNDLE_MAP,
    TIER_LADDER as SF_TIER_LADDER,
    DEFAULT_TIER_LEAD_INS, DEFAULT_TIER_CAPTIONS, DEFAULT_TIER_BRIDGES,
)
from smart_messaging import (
    TimeAwareSelector, MessageComposer,
    WARMUP_BY_TIME, ESCALATION_LEADS_BY_TIME, TENSION_BY_TIME,
)


# The 6-tier ladder in order of escalation
TIER_LADDER = [
    ContentTier.TIER_1_BODY_TEASE,
    ContentTier.TIER_2_TOP_TEASE,
    ContentTier.TIER_3_TOP_REVEAL,
    ContentTier.TIER_4_BOTTOM_REVEAL,
    ContentTier.TIER_5_FULL_EXPLICIT,
    ContentTier.TIER_6_CLIMAX,
]


class IntegratedEngine:
    """
    The core conversation state machine, fully integrated with all subsystems.

    Flow: message in → analyze → route to state handler → return actions
    Each handler uses avatar-specific templates, real pricing, and actual content.

    Script integration:
      - script_library: {persona_id: [Script, ...]} from ScriptFactory.build_full_library()
      - script_tracker: SubScriptTracker for per-sub dedup and progress tracking
      - When a sub enters the selling states, the engine pulls lead-ins, captions,
        dirty talk bridges, and bundle IDs directly from the assigned script's steps.
    """

    def __init__(
        self,
        avatars: Dict[str, AvatarConfig],
        catalog: Optional[ContentCatalog] = None,
        model_profile: Optional[ModelProfile] = None,
        attribution: Optional[AttributionEngine] = None,
        script_library: Optional[Dict[str, List[Script]]] = None,
        script_tracker: Optional[SubScriptTracker] = None,
    ):
        self.avatars = avatars
        self.catalog = catalog
        self.model = model_profile
        self.attribution = attribution
        self.analyzer = MessageAnalyzer()

        # Script system
        self.script_library = script_library or {}
        self.script_tracker = script_tracker or SubScriptTracker()

        # Time awareness + message variability
        self.time_selector = TimeAwareSelector()
        self.composer = MessageComposer()

        # State handler routing
        self.handlers = {
            SubState.NEW: self._handle_new,
            SubState.WELCOME_SENT: self._handle_welcome_response,
            SubState.QUALIFYING: self._handle_qualifying,
            SubState.CLASSIFIED: self._handle_classified,
            SubState.WARMING: self._handle_warming,
            SubState.TENSION_BUILD: self._handle_tension_build,
            SubState.FIRST_PPV_READY: self._handle_first_ppv,
            SubState.FIRST_PPV_SENT: self._handle_ppv_response,
            SubState.LOOPING: self._handle_loop,
            SubState.GFE_ACTIVE: self._handle_gfe,
            SubState.CUSTOM_PITCH: self._handle_custom_pitch,
            SubState.POST_SESSION: self._handle_post_session,
            SubState.RETENTION: self._handle_retention,
            SubState.RE_ENGAGEMENT: self._handle_re_engagement,
            SubState.COOLED_OFF: self._handle_cooled_off,
            SubState.DISQUALIFIED: self._handle_disqualified,
        }

    # ═══════════════════════════════════════════
    # MAIN ENTRY POINTS
    # ═══════════════════════════════════════════

    def process_message(self, sub: Subscriber, message: str) -> List[BotAction]:
        """Process an incoming message and return bot actions."""
        sub.add_message("sub", message)

        # Analysis
        analysis = {
            "sexual_intent": self.analyzer.detect_sexual_intent(message),
            "emotional_openness": self.analyzer.detect_emotional_openness(message),
            "whale_signals": self.analyzer.detect_whale_signals(message),
            "quality": self.analyzer.assess_message_quality(message),
        }

        # Extract qualifying data
        self._extract_data(sub, message)

        # Check for objections (override normal flow in selling states)
        objection = self.analyzer.detect_objection(message)
        if objection and sub.state in [
            SubState.FIRST_PPV_SENT, SubState.LOOPING, SubState.CUSTOM_PITCH
        ]:
            return self._handle_objection(sub, objection)

        # Check red flags
        self._check_red_flags(sub, message)

        # Route to state handler
        handler = self.handlers.get(sub.state, self._handle_retention)
        actions = handler(sub, message, analysis)

        # Track bot messages
        for action in actions:
            if action.message:
                sub.add_message("bot", action.message)

        return actions

    def process_new_subscriber(self, sub: Subscriber) -> List[BotAction]:
        """Handle a brand new subscriber (send welcome)."""
        return self._handle_new(sub, "", {})

    def check_for_re_engagement(self, sub: Subscriber) -> Optional[List[BotAction]]:
        """
        U7: Tiered re-engagement schedule based on days since last message.

        Tier schedule:
          3 days  → warmth nudge (miss you energy, no sell)
          7 days  → FOMO hook (something exciting is coming)
          14 days → soft pitch (come back, I have something for you)
          30 days → free content gift + memory callback (last resort retention)

        Only triggers for non-disqualified subs who haven't ghosted past the point
        of no return. After 4 attempts, stops proactive outreach.
        """
        if sub.state == SubState.DISQUALIFIED:
            return None
        days = sub.days_since_last_message
        if days is None:
            return None
        if sub.re_engagement_attempts >= 4:
            return None  # Already tried 4 times — don't spam

        avatar = self._get_avatar(sub)
        sub.re_engagement_attempts += 1
        sub.state = SubState.RE_ENGAGEMENT

        if days >= 30:
            # Tier 4: Free content gift + memory callback (last resort)
            callback = (
                f'I keep thinking about what you told me about {sub.callback_references[-1]}… '
                if sub.callback_references else ""
            )
            templates = [
                f"{callback}I wanted to send you something special. no strings, just… I've been thinking about you 💕",
                "okay I know it's been a while and that's on me too… I saved something for you. come back 🥺",
                "I don't do this for everyone but I've been thinking about you and I wanted to reach out one more time 💕",
            ]
        elif days >= 14:
            # Tier 3: Soft pitch (come back, I have something for you)
            templates = [
                "hey… I've been filming some things this week and every time I hit record I thought of you 😩 you should see what I've made",
                "I'm not gonna lie I've been waiting for you to come back because I have something that's literally made for you 🥵",
                "okay I really need you to come back because I've been holding onto something and it's driving me crazy 😈",
            ]
        elif days >= 7:
            # Tier 2: FOMO hook (something exciting is coming)
            templates = [
                "I don't know where you went but something big is coming and I want YOU to see it first 👀",
                "hey stranger… you picked a really bad week to disappear. just saying 😏",
                "I was literally just about to do something I think you'd lose your mind over and then I realized you haven't been here 😩",
            ]
        else:
            # Tier 1: Warmth nudge (3+ days, no sell)
            templates = [
                "hey troublemaker… miss me? 😏",
                "okay I'm just gonna say it — I've been thinking about you 🥺 where'd you go?",
                "I don't usually chase but… you're not just anyone to me 💕 come back",
                "damn… I didn't scare you off did I? 😅",
            ]

        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, templates, sub=sub),
            new_state=SubState.RE_ENGAGEMENT,
            delay_seconds=0,  # Proactive — send immediately
        )]

    def process_purchase(self, sub: Subscriber, amount: float, content_type: str = "ppv") -> List[BotAction]:
        """Handle an actual purchase event (webhook or sim 'paid').

        Called when a real purchase is confirmed — NOT guessed from message content.
        Returns post-purchase reaction + next tier PPV (or post-session transition).

        Args:
            sub: The subscriber who made the purchase.
            amount: Dollar amount of the purchase.
            content_type: Type of purchase ("ppv", "tip", "subscription").

        Returns:
            List of BotActions: [post-purchase reaction, lead-in message, next PPV]
            or [post-purchase reaction, post-session care] if all tiers complete.
        """
        sub.record_purchase(amount, content_type)
        avatar = self._get_avatar(sub)

        actions = []

        # Post-purchase excitement reaction
        reactions = [
            "omg you actually opened it 😍 you have no idea how happy that makes me",
            "mmm I was hoping you'd go for it 😏 what did you think?",
            "you just made my whole night 🥵 I knew you were different",
            "I can't believe you did that… I'm blushing rn 🙈",
            "yesss 😍 that's what I'm talking about. you're making me feel things",
            "I literally screamed when I saw you opened it 😩 you're the best",
        ]
        actions.append(BotAction(
            action_type="send_message",
            message=self._voice(avatar, reactions, sub=sub),
            delay_seconds=random.randint(5, 12),
        ))

        # Advance from FIRST_PPV_SENT to LOOPING after first purchase
        if sub.state == SubState.FIRST_PPV_SENT:
            sub.state = SubState.LOOPING
            sub.current_loop_number = 2  # Tier 1 done, ready for Tier 2

        # Check if all 6 tiers are complete
        loop = sub.current_loop_number
        if loop > 6:
            # All tiers purchased — transition to post-session
            sub.state = SubState.POST_SESSION
            post_msg = self._voice(avatar, [
                "damn… that was intense. you literally wore me out 😩",
                "I can't believe we just did all of that… you're something else 💕",
                "that was so much… I need to catch my breath 🥵",
            ], sub=sub)
            actions.append(BotAction(
                action_type="send_message",
                message=post_msg,
                new_state=SubState.POST_SESSION,
                delay_seconds=random.randint(15, 30),
            ))
            # Complete script and lock session
            self._complete_script(sub)
            SessionController.lock_session(sub, hours=6)
            sub.tier_no_count = 0
            sub.brokey_flagged = False
            sub.custom_declined = False
            sub.gfe_active = True
            return actions

        # Drop the next tier PPV
        tier = self._get_current_tier(sub)
        tier_cfg = TIER_CONFIG[tier]

        script = self._get_active_script(sub)
        step = self._get_script_step_for_tier(script, tier) if script else None

        # Pull lead-in messages from script step, or use defaults
        lead_in_templates = (step.message_templates if step else
                             DEFAULT_TIER_LEAD_INS.get(tier, [
                                 f"this next one is {tier_cfg['name'].lower()} level… you ready? 😈"
                             ]))

        # Pull captions from script step, or use defaults
        caption_templates = (step.ppv_caption_templates if step and step.ppv_caption_templates
                             else DEFAULT_TIER_CAPTIONS.get(tier, [
                                 f"{tier_cfg['name']}… exactly what it sounds like 😏"
                             ]))

        msg = self._voice(avatar, lead_in_templates, sub=sub)
        caption = random.choice(caption_templates)

        # Get bundle ID from script step
        bundle_id = step.conditions.get("bundle_id", "") if step and step.conditions else ""

        # Lead-in message
        actions.append(BotAction(
            action_type="send_message",
            message=msg,
            delay_seconds=random.randint(10, 20),
        ))

        # PPV action
        ppv_actions = self._build_ppv_action(sub, tier, caption, script_bundle_id=bundle_id)

        # Advance loop counter and track tier
        sub.current_loop_number = min(loop + 1, 7)  # 7 means all done
        self.script_tracker.advance_tier(sub.sub_id)

        # Determine next state
        if loop >= 6:
            next_state = SubState.POST_SESSION
        else:
            next_state = SubState.LOOPING
        sub.state = next_state

        if ppv_actions:
            ppv_actions[-1].new_state = next_state
        actions.extend(ppv_actions)

        # Mark pitch timestamp for same-day dedup (U13)
        sub.last_pitch_at = datetime.now()

        return actions

    # ═══════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════

    def _get_avatar(self, sub: Subscriber) -> AvatarConfig:
        """Get the avatar assigned to this subscriber."""
        if sub.persona_id and sub.persona_id in self.avatars:
            return self.avatars[sub.persona_id]
        # Default to first avatar — this means attribution failed or was missing
        first_key = list(self.avatars.keys())[0]
        logger.warning(
            "No avatar match for sub %s (persona_id=%r) — defaulting to %s",
            sub.sub_id, sub.persona_id, first_key,
        )
        sub.persona_id = first_key
        return self.avatars[first_key]

    def _voice(self, avatar: AvatarConfig, templates: List[str], sub: 'Subscriber' = None) -> str:
        """Select and style a message using the avatar's voice + dedup via composer."""
        # Use composer if we have a sub (for dedup tracking)
        if sub:
            msg = self.composer.compose(
                templates, sub=sub,
                add_opener=random.random() > 0.65,
                opener_style=random.choice(["casual", "flirty", "vulnerable"]),
            )
        else:
            msg = random.choice(templates)

        voice = avatar.persona.voice
        if voice.capitalization == "lowercase_casual" and random.random() > 0.5:
            msg = msg[0].lower() + msg[1:] if msg else msg
        if voice.emoji_use == "heavy" and not any(c in msg for c in "😈🔥💀😩😍🥵😏😘❤️"):
            msg += " " + random.choice(["😈", "🔥", "😏", "😘", "💀", "😩", "❤️"])
        return msg

    def _get_current_tier(self, sub: Subscriber) -> ContentTier:
        """Determine which pricing tier the sub is on based on their loop number."""
        loop = sub.current_loop_number
        if loop <= 0:
            return TIER_LADDER[0]
        idx = min(loop - 1, len(TIER_LADDER) - 1)
        return TIER_LADDER[idx]

    def _get_bundle_for_sub(self, sub: Subscriber, tier: ContentTier) -> Optional[ContentBundle]:
        """Get an available content bundle for this sub at this tier."""
        if not self.catalog:
            return None
        # Exclude bundles already sent to this sub
        sent_bundles = getattr(sub, '_sent_bundle_ids', [])
        return self.catalog.get_available_bundle(tier, exclude_ids=sent_bundles)

    # ═══════════════════════════════════════════
    # SCRIPT HELPERS
    # ═══════════════════════════════════════════

    def _get_scripts_for_sub(self, sub: Subscriber) -> List[Script]:
        """Get the script list for the sub's assigned persona."""
        if sub.persona_id and sub.persona_id in self.script_library:
            return self.script_library[sub.persona_id]
        # Try matching by avatar key → persona_id
        avatar = self._get_avatar(sub)
        pid = avatar.persona.persona_id
        return self.script_library.get(pid, [])

    def _assign_script(self, sub: Subscriber) -> Optional[Script]:
        """
        Assign the next available script to a subscriber.
        Filters by current time/day, then uses SubScriptTracker to pick next.
        """
        scripts = self._get_scripts_for_sub(sub)
        if not scripts:
            return None

        # Filter to time-appropriate scripts
        now = datetime.now()
        valid_scripts = self.time_selector.filter_scripts_by_time(
            scripts, hour=now.hour, is_weekend=(now.weekday() >= 5)
        )

        # Get next script index from tracker, but map to valid list
        script_idx = self.script_tracker.get_next_script(sub.sub_id)

        # Try to find the tracker's preferred script in the valid set
        preferred = scripts[script_idx % len(scripts)]
        if preferred in valid_scripts:
            script = preferred
        else:
            # Preferred isn't time-valid — pick from valid set
            script = random.choice(valid_scripts)

        sub.current_script_id = script.script_id
        sub.current_script_phase = ScriptPhase.INTRO
        return script

    def _get_active_script(self, sub: Subscriber) -> Optional[Script]:
        """Get the currently active script for a subscriber."""
        if not sub.current_script_id:
            return self._assign_script(sub)

        scripts = self._get_scripts_for_sub(sub)
        for s in scripts:
            if s.script_id == sub.current_script_id:
                return s

        # Script not found (shouldn't happen) — assign new one
        return self._assign_script(sub)

    def _get_script_step_for_tier(self, script: Script, tier: ContentTier) -> Optional[ScriptStep]:
        """
        Find the PPV_DROP or ESCALATION step in a script that matches a given tier.
        Each script has one step per tier, identified by conditions["tier"].
        """
        if not script:
            return None
        tier_val = tier.value
        for step in script.steps:
            if step.conditions and step.conditions.get("tier") == tier_val:
                return step
        return None

    def _get_bridge_step_before_tier(self, script: Script, tier: ContentTier) -> Optional[ScriptStep]:
        """
        Find the REACTION (dirty talk bridge) step that comes right before
        a given tier's PPV step in the script.
        """
        if not script:
            return None
        tier_val = tier.value
        prev_step = None
        for step in script.steps:
            if step.conditions and step.conditions.get("tier") == tier_val:
                # The previous step should be a REACTION bridge
                if prev_step and prev_step.phase == ScriptPhase.REACTION:
                    return prev_step
                return None
            prev_step = step
        return None

    def _get_cooldown_step(self, script: Script) -> Optional[ScriptStep]:
        """Get the COOLDOWN step from a script."""
        if not script:
            return None
        for step in script.steps:
            if step.phase == ScriptPhase.COOLDOWN:
                return step
        return None

    def _complete_script(self, sub: Subscriber):
        """Mark the current script as complete and advance the tracker."""
        if sub.current_script_id:
            sub.scripts_completed.append(sub.current_script_id)
        self.script_tracker.advance_script(sub.sub_id)
        sub.current_script_id = None
        sub.current_script_phase = None

    def _build_ppv_action(
        self,
        sub: Subscriber,
        tier: ContentTier,
        caption: str,
        lead_in: str = "",
        script_bundle_id: str = "",
    ) -> List[BotAction]:
        """
        Build PPV send action with proper pricing and content bundle.

        If script_bundle_id is provided (from the script step's conditions),
        it's used as the primary bundle reference. The SubScriptTracker
        records it to prevent re-sends across sessions.

        If a real ContentCatalog is available, the catalog bundle is used
        for the actual content delivery.
        """
        price = get_tier_price(tier)
        catalog_bundle = self._get_bundle_for_sub(sub, tier)

        actions = []
        if lead_in:
            actions.append(BotAction(
                action_type="send_message",
                message=lead_in,
                delay_seconds=random.randint(5, 15),
            ))

        # Determine bundle ID — prefer script-assigned, fall back to catalog
        bundle_id = script_bundle_id or (catalog_bundle.bundle_id if catalog_bundle else None)

        # Track in SubScriptTracker for dedup
        if bundle_id:
            self.script_tracker.mark_bundle_sent(sub.sub_id, bundle_id)

        # Track in catalog if using real content
        if catalog_bundle and catalog_bundle.bundle_context:
            if not hasattr(sub, '_sent_bundle_ids'):
                sub._sent_bundle_ids = []
            sub._sent_bundle_ids.append(catalog_bundle.bundle_id)
            catalog_bundle.times_sent += 1

        actions.append(BotAction(
            action_type="send_ppv",
            ppv_price=price,
            ppv_caption=caption,
            content_id=bundle_id,
            message="",
            metadata={"tier": tier.value, "bundle_id": bundle_id},
            delay_seconds=random.randint(3, 10),
        ))
        return actions

    def _extract_data(self, sub: Subscriber, message: str):
        """Extract qualifying data from message."""
        age = self.analyzer.extract_age(message)
        if age:
            sub.qualifying.age = age
        loc = self.analyzer.extract_location(message)
        if loc:
            sub.qualifying.location = loc
        job = self.analyzer.extract_occupation(message)
        if job:
            sub.qualifying.occupation = job
        rel = self.analyzer.detect_relationship_status(message)
        if rel:
            sub.qualifying.relationship_status = rel

        quality = self.analyzer.assess_message_quality(message)
        if quality["is_one_word"]:
            sub.one_word_reply_streak += 1
        else:
            sub.one_word_reply_streak = 0
        if quality["is_paragraph"]:
            sub.qualifying.message_length = "paragraph"

        # Store callback references
        if len(message.split()) >= 5:
            sub.add_callback_reference(message[:100])

        # Whale signals
        for signal in self.analyzer.detect_whale_signals(message):
            if signal not in sub.emotional_hooks:
                sub.emotional_hooks.append(signal)

    def _check_red_flags(self, sub: Subscriber, message: str):
        """Check for timewaster red flags."""
        msg = message.lower()
        if any(w in msg for w in ["free", "send me free", "free pic"]):
            sub.asked_for_free_content += 1
        if any(w in msg for w in ["meet", "meetup", "in person", "come over"]):
            sub.asked_for_meetup = True

    # ═══════════════════════════════════════════
    # STATE HANDLERS
    # ═══════════════════════════════════════════

    def _handle_new(self, sub, message, analysis) -> List[BotAction]:
        """Send avatar-specific welcome message. Detects returning users."""
        avatar = self._get_avatar(sub)

        # U7: Detect returning user — don't ask "what made you subscribe?" again
        if sub.message_count > 0 or sub.recent_messages:
            returning_templates = [
                "hey you're back 😏 I was hoping you'd come find me again",
                "there you are 💕 I've been thinking about our last conversation",
                "missed you babe 😘 where have you been hiding?",
                "oh hey 😏 I knew you'd be back… they always come back",
                "welcome back 💕 I was just thinking about you actually",
            ]
            msg = self._voice(avatar, returning_templates)
        else:
            # First-time subscriber
            templates = avatar.welcome_messages or [
                "hey! what made you want to subscribe? I'm always curious 💕"
            ]
            msg = self._voice(avatar, templates)
        sub.state = SubState.WELCOME_SENT

        return [BotAction(
            action_type="send_message",
            message=msg,
            new_state=SubState.WELCOME_SENT,
            delay_seconds=random.randint(8, 20),
        )]

    def _handle_welcome_response(self, sub, message, analysis) -> List[BotAction]:
        """Process first response. Start qualifying — or skip entirely if fan is hot."""
        avatar = self._get_avatar(sub)
        sexual = analysis.get("sexual_intent", 0)

        # Zero-qualifying fast path: if the fan's FIRST message shows high sexual interest
        # or body-focused desire, skip qualifying entirely → straight to WARMING.
        # A fan who says "your amazing tits brought me here" is already qualified as HORNY.
        # Forcing qualifying questions kills momentum and loses the sale.
        if sexual >= 0.3 or _BUY_SIGNALS.search(message):
            sub.sub_type = SubType.HORNY
            sub.qualifying_questions_asked = 1  # Credit them 1 Q (the welcome was a Q)
            sub.state = SubState.WARMING
            return self._handle_warming(sub, message, analysis)

        # Normal path: fan gave a casual/non-sexual first reply → ask qualifying questions
        return self._ask_qualifying_question(sub, avatar, intro=True)

    def _handle_qualifying(self, sub, message, analysis) -> List[BotAction]:
        """Continue qualification using avatar-specific questions."""
        avatar = self._get_avatar(sub)

        # Early timewaster detection — don't waste questions on freeloaders
        if sub.asked_for_free_content >= 2 or (
            sub.one_word_reply_streak >= 3 and sub.message_count >= 4
        ):
            sub.sub_type = SubType.TIMEWASTER
            sub.state = SubState.DISQUALIFIED
            return self._handle_disqualified(sub, message, analysis)

        # Buy signal detection — if fan asks for content, fast-track through qualifying
        # No minimum question requirement — a buy signal IS qualification
        if _BUY_SIGNALS.search(message):
            sub.sub_type = SubType.HORNY
            sub.state = SubState.WARMING
            return self._handle_warming(sub, message, analysis)

        # Dynamic qualifying gate: 1 question enough if very sexual, 2 otherwise
        min_questions = 1 if analysis.get("sexual_intent", 0) >= 0.4 else 2
        if analysis.get("sexual_intent", 0) >= 0.2 and sub.qualifying_questions_asked >= min_questions:
            sub.sub_type = SubType.HORNY
            sub.state = SubState.WARMING
            return self._handle_warming(sub, message, analysis)

        # Affirmative to current question → advance index without re-asking
        if self.analyzer.detect_affirmative(message):
            sub.qualifying_questions_asked = max(
                sub.qualifying_questions_asked,
                sub.qualifying_questions_asked  # already incremented by _ask_qualifying_question
            )
            # Don't increment here — it was already incremented when the question was asked.
            # Just fall through to check if we have enough.

        # Check if we have enough info to classify
        has_enough = (
            sub.qualifying_questions_asked >= 3 or
            (sub.qualifying.age and sub.qualifying.occupation) or
            sub.message_count >= 12
        )

        if has_enough:
            sub.sub_type = self.analyzer.classify_sub_type(sub)
            sub.state = SubState.CLASSIFIED
            return self._handle_classified(sub, message, analysis)

        return self._ask_qualifying_question(sub, avatar)

    def _ask_qualifying_question(self, sub, avatar, intro=False) -> List[BotAction]:
        """
        Ask the next avatar-specific qualifying question.

        Uses qualifying_questions_asked as a direct index into the question list —
        this guarantees we never ask the same question twice, regardless of whether
        the extractor successfully parsed the fan's answer.
        """
        questions = avatar.qualifying_questions
        if not questions:
            sub.sub_type = self.analyzer.classify_sub_type(sub)
            sub.state = SubState.CLASSIFIED
            return self._handle_classified(sub, "", {})

        # Direct index — advance one question per turn, no repeats
        q_idx = sub.qualifying_questions_asked
        if q_idx >= len(questions):
            sub.sub_type = self.analyzer.classify_sub_type(sub)
            sub.state = SubState.CLASSIFIED
            return self._handle_classified(sub, "", {})

        selected_q = questions[q_idx]

        if intro:
            intros = [
                "omg I love that 😊 okay so ",
                "aww that's sweet 🥰 okay I have to ask... ",
                "okay I like you already 👀 ",
            ]
            msg = random.choice(intros) + selected_q["question"]
        else:
            transitions = [
                "okay next question lol... ",
                "hmm interesting 👀 okay so ",
                "I love that honestly 😊 ",
                "wait really?? okay so ",
            ]
            msg = random.choice(transitions) + selected_q["question"]

        sub.qualifying_questions_asked += 1
        msg = self._voice(avatar, [msg])
        sub.state = SubState.QUALIFYING

        return [BotAction(
            action_type="send_message",
            message=msg,
            new_state=SubState.QUALIFYING,
            delay_seconds=random.randint(8, 20),
        )]

    def _handle_classified(self, sub, message, analysis) -> List[BotAction]:
        """Route based on classification using avatar voice."""
        avatar = self._get_avatar(sub)

        if sub.sub_type == SubType.TIMEWASTER:
            sub.state = SubState.DISQUALIFIED
            return [BotAction(
                action_type="send_message",
                message=self._voice(avatar, [
                    "I love chatting but I save the best stuff for my real ones 😉",
                    "hmm you seem fun but I spend time with guys who really appreciate me 💕",
                ]),
                new_state=SubState.DISQUALIFIED,
            )]

        if sub.sub_type == SubType.HORNY:
            sub.state = SubState.WARMING
            return [BotAction(
                action_type="send_message",
                message=self._voice(avatar, [
                    "mmm I can already tell you're trouble 😈",
                    "okay you're giving me a certain energy rn and I'm into it 👀",
                ]),
                new_state=SubState.WARMING,
                delay_seconds=random.randint(5, 15),
            )]

        # Attracted / Curious / Unknown → standard warming
        sub.state = SubState.WARMING
        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, [
                "you're actually really easy to talk to… that's rare for me 🥰",
                "something about you is different and I can't figure it out yet",
                "okay I'm not gonna lie you have a vibe and I'm curious about it 👀",
            ]),
            new_state=SubState.WARMING,
            delay_seconds=random.randint(10, 25),
        )]

    def _handle_warming(self, sub, message, analysis) -> List[BotAction]:
        """Build rapport using sex-adjacent language. Let HIM go first.
        But if he doesn't escalate after 3 turns, the bot starts leading.
        Uses time-appropriate message pools + dedup via composer."""
        avatar = self._get_avatar(sub)
        sexual = analysis.get("sexual_intent", 0)
        hour = datetime.now().hour

        # Buy signal detection → fast-track to selling
        if _BUY_SIGNALS.search(message) and sub.qualifying_questions_asked >= 1:
            sub.state = SubState.FIRST_PPV_READY
            return self._handle_first_ppv(sub, message, analysis)

        # Track warming turns
        if not hasattr(sub, '_warming_turns'):
            sub._warming_turns = 0
        sub._warming_turns += 1

        # Sub went sexual → advance to tension build
        if sexual >= 0.2:
            sub.qualifying.initiated_sexual = True
            sub._warming_turns = 0
            sub.state = SubState.TENSION_BUILD
            return self._handle_tension_build(sub, message, analysis)

        # After 3 turns without escalation, bot starts leading — TIME AWARE
        if sub._warming_turns >= 3:
            sub._warming_turns = 0
            sub.state = SubState.TENSION_BUILD
            escalation_leads = self.time_selector.get_escalation_leads(hour)
            return [BotAction(
                action_type="send_message",
                message=self._voice(avatar, escalation_leads, sub=sub),
                new_state=SubState.TENSION_BUILD,
                delay_seconds=random.randint(15, 30),
            )]

        # Standard sex-adjacent warm-up — TIME AWARE
        warmup = self.time_selector.get_warmup_messages(hour)

        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, warmup, sub=sub),
            delay_seconds=random.randint(15, 40),
        )]

    def _handle_tension_build(self, sub, message, analysis) -> List[BotAction]:
        """Sub went sexual or bot escalated. Build heat then advance to first PPV.
        This state should only last 1 turn — any response advances.
        Uses time-appropriate tension messages + dedup."""
        avatar = self._get_avatar(sub)
        hour = datetime.now().hour

        # Buy signal → skip straight to PPV
        if _BUY_SIGNALS.search(message):
            sub.state = SubState.FIRST_PPV_READY
            return self._handle_first_ppv(sub, message, analysis)

        tension = self.time_selector.get_tension_messages(hour)

        msg = self._voice(avatar, tension, sub=sub)
        sub.state = SubState.FIRST_PPV_READY

        return [BotAction(
            action_type="send_message",
            message=msg,
            new_state=SubState.FIRST_PPV_READY,
            delay_seconds=random.randint(8, 20),
        )]

    @staticmethod
    def _pitched_today(sub: Subscriber) -> bool:
        """Return True if a PPV pitch was already sent to this sub today (same-day dedup).
        Prevents sending two pitches in one calendar day, which SirenCY data shows
        destroys trust and signals automation to the subscriber."""
        if sub.last_pitch_at is None:
            return False
        return sub.last_pitch_at.date() == datetime.now().date()

    def _handle_first_ppv(self, sub, message, analysis) -> List[BotAction]:
        """Drop the first PPV — Tier 1: $27.38 Full Body Tease.
        Assigns a script and pulls lead-ins + captions from its Tier 1 step."""
        avatar = self._get_avatar(sub)
        tier = ContentTier.TIER_1_BODY_TEASE
        sub.current_loop_number = 1
        sub.state = SubState.FIRST_PPV_SENT

        # Assign a script for this session
        script = self._assign_script(sub)
        step = self._get_script_step_for_tier(script, tier) if script else None

        # Pull lead-ins from script step, or use defaults
        lead_in_templates = (step.message_templates if step else
                             DEFAULT_TIER_LEAD_INS[tier])
        lead_in = self._voice(avatar, lead_in_templates, sub=sub)

        # Pull captions from script step, or use defaults
        caption_templates = (step.ppv_caption_templates if step and step.ppv_caption_templates
                             else DEFAULT_TIER_CAPTIONS[tier])
        caption = random.choice(caption_templates)

        # Get bundle ID from script step
        bundle_id = step.conditions.get("bundle_id", "") if step and step.conditions else ""

        actions = self._build_ppv_action(sub, tier, caption, lead_in, bundle_id)
        actions[-1].new_state = SubState.FIRST_PPV_SENT

        # Mark pitch timestamp for same-day dedup (U13)
        sub.last_pitch_at = datetime.now()

        # Track tier progress
        self.script_tracker.advance_tier(sub.sub_id)

        return actions

    def _handle_ppv_response(self, sub, message, analysis) -> List[BotAction]:
        """Handle fan message while first PPV is pending (not yet paid).

        Responds conversationally — builds desire, teases about the pending content.
        Does NOT advance state. Purchase events are handled separately via process_purchase().
        """
        avatar = self._get_avatar(sub)

        # Fan is chatting while PPV is pending — keep building desire
        teases = [
            "you haven't even opened it yet 😏 what are you waiting for?",
            "mmm I'm so nervous for you to see it 🙈 the anticipation is killing me",
            "I put that together just for you… don't leave me hanging 😩",
            "the longer you wait the more I want you to see what I did 😈",
            "I'm literally sitting here waiting to hear what you think 🥺",
            "you have no idea what's waiting for you 😏 just open it already",
        ]

        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, teases, sub=sub),
            delay_seconds=random.randint(10, 25),
        )]

    def _handle_loop(self, sub, message, analysis) -> List[BotAction]:
        """Handle fan message while a PPV is pending in the selling loop.

        Responds conversationally — keeps energy high while fan decides on the pending PPV.
        Does NOT drop another PPV. PPV drops happen only via process_purchase().
        """
        avatar = self._get_avatar(sub)

        # Fan is chatting while PPV is pending — keep the heat up
        teases = [
            "mmm you're making me want to show you everything right now 😈",
            "I can tell you want more… just open it and see 😏",
            "you're driving me crazy just sitting there 🥵 open it",
            "I promise you won't regret it… I put extra effort into this one 😘",
            "the way you talk to me makes me want to give you everything 😩",
            "you have no idea how much I want you to see this 😍",
        ]

        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, teases, sub=sub),
            delay_seconds=random.randint(10, 25),
        )]

    def _handle_custom_pitch(self, sub, message, analysis) -> List[BotAction]:
        """
        Pitch custom content. Handles three scenarios:
        1. First time in this state → pitch the custom
        2. Sub declines → graceful exit to POST_SESSION
        3. Sub is interested → collect details (future: order system)
        """
        avatar = self._get_avatar(sub)
        msg_lower = message.lower()
        sc = SessionController()

        # Check for decline signals
        decline_signals = [
            "no", "nah", "not right now", "maybe later", "i'm good",
            "pass", "too much", "can't afford", "not interested",
            "no thanks", "i'm okay", "don't want", "skip",
        ]
        is_decline = any(sig in msg_lower for sig in decline_signals)

        if is_decline or sub.custom_declined:
            # Graceful decline → move to POST_SESSION
            sub.custom_declined = True
            msg = sc.get_custom_decline_response()
            sub.state = SubState.POST_SESSION
            return [BotAction(
                action_type="send_message",
                message=msg,
                new_state=SubState.POST_SESSION,
                delay_seconds=random.randint(10, 25),
            )]

        # Try to pull from the script's CUSTOM_TEASE step
        script = self._get_active_script(sub)
        custom_templates = None
        if script:
            for step in script.steps:
                if step.phase == ScriptPhase.CUSTOM_TEASE:
                    custom_templates = step.message_templates
                    break

        discovery = custom_templates or [
            "okay you've seen the tease… but what would you want me to make JUST for you? 😈",
            "be specific… what's your dream video? outfit? position? I want to know everything 😏",
            "if I could film anything right now just for you… what would it be? tell me your fantasy",
        ]

        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, discovery, sub=sub),
            delay_seconds=random.randint(10, 25),
            metadata={"pitch_phase": "discovery"},
        )]

    def _handle_post_session(self, sub, message, analysis) -> List[BotAction]:
        """
        Post-session GFE care. Uses script's COOLDOWN step, then marks
        script complete and LOCKS the session for 6 hours.
        No new selling session can start until the lock expires.
        """
        avatar = self._get_avatar(sub)

        # Try to pull from the script's COOLDOWN step
        script = self._get_active_script(sub)
        cooldown_step = self._get_cooldown_step(script)

        post_care = (cooldown_step.message_templates if cooldown_step else [
            "damn… I needed that. you literally wore me out 😩",
            "that was so intense… I wish I could just lay with you after 💕",
            "you better come back tomorrow. I'm not done with you 😈",
        ])

        msg = self._voice(avatar, post_care, sub=sub)

        # Mark script complete — next session gets a fresh script
        self._complete_script(sub)

        # LOCK the session — no new selling for 6 hours
        SessionController.lock_session(sub, hours=6)

        # Reset objection tracking for next session
        sub.tier_no_count = 0
        sub.brokey_flagged = False
        sub.custom_declined = False

        sub.state = SubState.RETENTION
        sub.gfe_active = True

        return [BotAction(
            action_type="send_message",
            message=msg,
            new_state=SubState.RETENTION,
            delay_seconds=random.randint(20, 45),
        )]

    def _handle_gfe(self, sub, message, analysis) -> List[BotAction]:
        """
        Full GFE mode using expanded template pools (80+ unique responses).
        Contextually selects from: flirty banter, sweet/intimate, playful
        teasing, desire building, late night, morning, jealousy play.
        Time-aware selection ensures messages match the vibe.
        """
        avatar = self._get_avatar(sub)
        sc = SessionController()

        # Get time-appropriate GFE response
        msg = sc.get_gfe_response(sub, context="general")

        # Mix in avatar-specific touchpoints occasionally
        if avatar.gfe_touchpoints and random.random() > 0.6:
            msg = random.choice(avatar.gfe_touchpoints)

        # Add callback-based personalization if we have references
        if sub.callback_references and random.random() > 0.7:
            ref = random.choice(sub.callback_references[-5:])
            msg = f"I keep thinking about what you told me about {ref}… it's stuck in my head tbh 💕"

        # Occasional jealousy play (15% chance)
        if random.random() > 0.85:
            msg = random.choice(GFE_JEALOUSY_PLAY)

        return [BotAction(
            action_type="send_message",
            message=msg,
            delay_seconds=random.randint(15, 45),
        )]

    def _handle_retention(self, sub, message, analysis) -> List[BotAction]:
        """
        Long-term retention with session lock enforcement.

        U4: COOLING period — if brokey_flagged and within 5-day cooldown,
          send warmth-only. Auto-reset flag on day 6.

        If session is LOCKED (within 6 hours of last session):
          - Sexual intent → desire building + "come back tomorrow"
          - Normal chat → expanded GFE templates

        If session is UNLOCKED:
          - Sexual intent → restart selling with fresh script (unless already
            pitched today — U13 same-day dedup)
          - Normal chat → GFE
        """
        avatar = self._get_avatar(sub)
        sc = SessionController()
        sexual = analysis.get("sexual_intent", 0) >= 0.3

        # U4: Auto-reset brokey flag after 5-day cooling
        if sc.should_reset_brokey(sub):
            logger.debug("COOLING period elapsed for %s — resetting brokey flag", sub.sub_id)
            sub.brokey_flagged = False
            sub.tier_no_count = 0

        # U4: COOLING period — warmth only, no selling
        if sc.is_in_brokey_cooldown(sub):
            logger.debug("Sub %s in COOLING period — warmth only", sub.sub_id)
            return [BotAction(
                action_type="send_message",
                message=sc.get_brokey_cooling_response(sub),
                delay_seconds=random.randint(20, 45),
            )]

        if sexual and sc.is_session_locked(sub):
            # He wants more but session is locked — build desire, set boundaries
            push_count = getattr(sub, '_session_push_count', 0)
            msg = sc.get_session_lock_response(sub, push_count)
            sub._session_push_count = push_count + 1
            return [BotAction(
                action_type="send_message",
                message=msg,
                delay_seconds=random.randint(15, 40),
            )]

        elif sexual and not sc.is_session_locked(sub):
            # Same-day dedup (U13): if already pitched today, send GFE instead.
            # Sending two pitches in one day signals automation and destroys trust.
            if self._pitched_today(sub):
                logger.debug("Same-day pitch dedup: already pitched %s today → routing to GFE", sub.sub_id)
                return self._handle_gfe(sub, message, analysis)

            # Session unlocked + sexual intent → new session with fresh script
            sub.state = SubState.WARMING
            sub.current_loop_number = 0
            sub.current_script_id = None
            sub.current_script_phase = None
            sub.tier_no_count = 0
            sub.brokey_flagged = False
            sub._session_push_count = 0
            return self._handle_warming(sub, message, analysis)

        else:
            # Normal chat — use expanded GFE
            return self._handle_gfe(sub, message, analysis)

    def _handle_re_engagement(self, sub, message, analysis) -> List[BotAction]:
        """Re-engage after ghosting."""
        avatar = self._get_avatar(sub)
        sub.re_engagement_attempts += 1

        templates = [
            "hey troublemaker… miss me? 😏",
            "damn… I didn't scare you off did I?",
            "I'm still thinking about last time… bet you are too 👀",
        ]

        sub.state = SubState.RETENTION
        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, templates),
            new_state=SubState.RETENTION,
        )]

    def _handle_cooled_off(self, sub, message, analysis) -> List[BotAction]:
        """Sub came back after going quiet."""
        sub.ghost_count += 1
        sub.state = SubState.RETENTION
        return self._handle_retention(sub, message, analysis)

    def _handle_disqualified(self, sub, message, analysis) -> List[BotAction]:
        """Timewaster — minimal engagement."""
        avatar = self._get_avatar(sub)

        if sub.spending.is_buyer:
            sub.sub_type = SubType.ATTRACTED
            sub.state = SubState.WARMING
            return self._handle_warming(sub, message, analysis)

        return [BotAction(
            action_type="send_message",
            message=self._voice(avatar, [
                "I love chatting but I save the best stuff for my supporters 😉",
                "you know where to find me when you're serious… I don't chase 💕",
            ]),
            delay_seconds=random.randint(120, 300),
        )]

    # ═══════════════════════════════════════════
    # OBJECTION HANDLING (avatar-specific)
    # ═══════════════════════════════════════════

    def _handle_objection(self, sub: Subscriber, objection: ObjectionType) -> List[BotAction]:
        """
        Handle objections using the 3-No Rule with ego-driven escalation.
        
        No 1: Subtle ego bruise ("oh you don't have to baby")
        No 2: Medium ego bruise ("not everyone can keep up with me")
        No 3: Direct ego bruise ("I thought you were different")
        After 3: Brokey treatment → desire build → dismiss → GFE
        """
        avatar = self._get_avatar(sub)
        sc = SessionController()
        
        # Map ObjectionType enum to string key
        obj_key = objection.value.upper() if hasattr(objection, 'value') else str(objection).split('.')[-1]
        
        # Get ego-driven response based on no count
        msg, next_action = sc.handle_tier_objection(sub, avatar, obj_key)
        
        if next_action == "brokey":
            # 3rd No — Full brokey treatment
            brokey_msgs = sc.get_brokey_response(sub, avatar)
            actions = [
                BotAction(
                    action_type="send_message",
                    message=msg,  # The 3rd ego bruise
                    delay_seconds=random.randint(10, 20),
                ),
            ]
            # Send brokey treatment with delays
            for i, brokey_msg in enumerate(brokey_msgs):
                actions.append(BotAction(
                    action_type="send_message",
                    message=brokey_msg,
                    delay_seconds=random.randint(20, 45) * (i + 1),
                ))
            
            # Move to GFE — he's done buying for now
            sub.state = SubState.GFE_ACTIVE
            sub.gfe_active = True
            actions[-1].new_state = SubState.GFE_ACTIVE
            return actions
        
        else:
            # No 1 or 2 — ego bruise but stay in selling state
            return [BotAction(
                action_type="send_message",
                message=msg,
                delay_seconds=random.randint(10, 30),
            )]
