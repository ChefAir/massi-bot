"""
Massi-Bot Bot Engine - Avatar Tier Captions
Per-avatar caption pools for all 6 pricing tiers.

These provide the middle layer in the caption fallback chain:
  1. Theme-specific tier_captions (e.g., "stressed_after_meeting")
  2. Avatar-level tier captions (this file) ← NEW
  3. Generic DEFAULT_TIER_CAPTIONS (in script_factory.py)

Each avatar has 3-4 unique captions per tier that match its
psychological voice and target demo. These ensure that even themes
without custom captions still sound like the right persona.

10 avatars × 6 tiers × 3-4 captions = ~220 persona-specific captions
"""

from onboarding import ContentTier


AVATAR_TIER_CAPTIONS = {

    # ═══════════════════════════════════════════════════════════
    # GIRL BOSS — hustle, stress relief, boss bitch energy
    # ═══════════════════════════════════════════════════════════
    "girl_boss": {
        ContentTier.TIER_1_BODY_TEASE: [
            "this is what I look like when I'm off the clock and nobody's watching 😈",
            "business casual just became business casual-ty… enjoy 😏",
            "the outfit I wear when the zoom camera is off… you're welcome",
            "CEO by day but right now? just a girl who needs attention 💕",
            # U9: Price anchoring — establishes $200 as the reference point
            "most of what I make goes for $200 but I wanted to start you off right… intro price, just $27 today 😏",
            "I usually charge way more for this but you're new and I like you… $27 to see what all the fuss is about 😈",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the blazer came off and so did my professionalism 😏",
            "this is the version of me that doesn't show up to meetings",
            "half boss bitch half something else entirely right now",
            "the work shirt is barely hanging on and honestly neither am I",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "no more dress code. no more rules. just me 🥵",
            "my board of directors would NOT approve of this content 😈",
            "off the clock and off the shirt… the full after-hours experience",
            "this is what success looks like when nobody's in the room",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "business on top and absolutely nothing on the bottom… power move 😈",
            "if you could see me from the waist down during a zoom call… this is it",
            "the bottom half has left the building and I don't miss it 🥵",
            "top on bottoms gone because I make the rules around here",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "no clothes no titles no boundaries just me taking what I want 🥵",
            "this is what happens when a boss bitch finally lets go",
            "I run a business by day but at night I run something else entirely 😈",
            "fully free and fully in charge of what happens next",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "the biggest power move of the night and I screamed through every second 😈",
            "I just finished harder than any quarterly close 🥵 you're welcome",
            "the stress is officially gone and so is everything else… grand finale",
            "CEO orgasm energy and I recorded every moment for you 😈",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # HOUSEWIFE — domestic, cooking, feminine, wifey fantasy
    # ═══════════════════════════════════════════════════════════
    "housewife": {
        ContentTier.TIER_1_BODY_TEASE: [
            "just a wife doing wife things in barely anything 😏",
            "the house is clean and so is this outfit… barely there",
            "domestic goddess energy in something you'd lose your mind over 💕",
            "I do everything around here and I look good doing it",
            # U9: Price anchoring
            "my regulars pay $200 for the full experience but you're getting the intro for $27… consider yourself lucky 💕",
            "this starts at $27 but by the end of our session you'll understand why the full thing costs $200 😏",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the top is sliding down and I'm not fixing it this time 😏",
            "wifey material but the material is disappearing up top",
            "you should see what's under the apron… actually you're about to",
            "good wives don't do this but I was never that good 😈",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "the apron can only hide so much and now it's hiding nothing 🥵",
            "top off and the house suddenly feels a lot warmer",
            "this is what I look like when nobody comes home on time 😈",
            "no shirt just a wife who's tired of being good",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "dinner is on the table but the bottoms are on the floor 😈",
            "from the waist down I am NOT cleaning the house right now",
            "the only thing I'm wearing below the waist is confidence 🥵",
            "top back on but below that? she's gone wild in the kitchen",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "the whole house is my playground and tonight there are no rules 🥵",
            "fully unclothed in every room and I don't care anymore",
            "this wife has nothing left to take off and nothing left to hide 😈",
            "naked in the house I keep spotless doing very dirty things",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "I finished in the bedroom I make every morning and it was the best mess I've ever made 😈",
            "the neighbors might have heard and I genuinely do not care 🥵",
            "every room in this house just witnessed something unforgettable",
            "wifey went ALL the way and the footage is insane 😈",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SOUTHERN BELLE — country, fire, stars, whiskey, trucks
    # ═══════════════════════════════════════════════════════════
    "southern_belle": {
        ContentTier.TIER_1_BODY_TEASE: [
            "just a country girl in cutoffs and a whole lot of trouble 🤠",
            "the firelight is doing things to this body and I filmed it for you 😏",
            "southern hospitality in its purest form… barely dressed",
            "mama didn't raise me to act like this but here we are 🤠😈",
            # U9: Price anchoring
            "sugar I normally ask $200 for the full show but I'm letting you in for $27 today… don't tell the others 😏🤠",
            "most darlin… most of what I make goes for way more than this. you're getting the sweet intro deal at $27 💕",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the flannel is unbuttoned and the whiskey is responsible 😏🤠",
            "everything up top is about to get a whole lot more country",
            "pulling this shirt down slow like a honky tonk song",
            "the top is barely hanging on like a bull rider at 7 seconds 🤠",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "the flannel hit the dirt and there ain't no putting it back on 🥵",
            "topless under the stars and not a soul around to tell 🤠",
            "this is what the good lord gave me and I'm sharing it with you",
            "shirt's gone and the firelight is painting everything gold 😈",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "the cutoffs didn't survive the night and I am not sorry 😈🤠",
            "top back on but the bottoms are somewhere in the grass",
            "below the belt it's all country and zero rules 🥵",
            "the bottoms came off faster than a cold beer on a hot day 🤠",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "born free living free wearing nothing under God's sky 🥵🤠",
            "not a stitch on and the stars are the only witnesses",
            "fully bare and fully wild out here in the country tonight 😈",
            "nature girl at her most natural and I mean NOTHING on",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "lord have mercy I just screamed so loud the coyotes answered 🤠🥵",
            "the grand finale out here under the stars and I lost my mind",
            "I finished so hard I scared the wildlife 😈 best night ever",
            "country girl climax content and every second is yours 🤠🥵",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # CRYPTO BABE — money, charts, portfolio, trading, flex
    # ═══════════════════════════════════════════════════════════
    "crypto_babe": {
        ContentTier.TIER_1_BODY_TEASE: [
            "this is what my portfolio bought… the outfit and what's in it 😏📈",
            "charts are closed but the show is just opening for you",
            "dressed like money but about to be wearing a lot less of it 😈",
            "the only green you need to see tonight is this lingerie 📈",
            # U9: Price anchoring
            "babe my top stuff goes for $200 but you're getting the $27 entry point right now… treat it like an early investment 📈😈",
            "best ROI you'll make today: $27 intro vs $200 full bundle. start here 😏",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the silk robe is sliding off like a crypto dip… slow then fast 😏",
            "top half teasing like a bull trap… it looks like it's staying on but it's not 📈",
            "this is the preview before the real pump 😈",
            "pulling down the top like I'm pulling profits… aggressively",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "fully topless and more exposed than my long positions 🥵📈",
            "the shirt is gone like my stop-losses at 3am",
            "no more teasing. this is the breakout you've been waiting for 😈",
            "charts up top? no. just me. all of me. 📈🥵",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "portfolio up bottoms down and I don't mean the market 😈",
            "from the waist down I'm trading in a different kind of asset 🥵",
            "the bottom dropped out and that's the point 📈😈",
            "top covered bottom exposed… like a good short position",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "fully unclothed fully unhedged fully yours 🥵📈",
            "nothing on and nothing left to the imagination… all-in 😈",
            "this is max exposure and I'm not talking about my portfolio",
            "every position open every asset bare nothing held back 📈🥵",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "I just hit my personal all-time high and screamed through every candle 📈🥵",
            "the biggest climax of the night and the charts had nothing to do with it 😈",
            "I finished harder than a Bitcoin pump and filmed the whole rally 🥵",
            "grand finale: toys deployed gains realized screaming achieved 📈😈",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SPORTS GIRL — game day, jersey, bets, halftime, scores
    # ═══════════════════════════════════════════════════════════
    "sports_girl": {
        ContentTier.TIER_1_BODY_TEASE: [
            "jersey on nothing else game day vibes only 🏈😈",
            "this is what the other side of the screen looks like on game day 😏",
            "the best view isn't on the field it's right here",
            "dressed for the game but barely dressed at all 🏈",
            # U9: Price anchoring
            "my full game night experience runs $200 but the intro is only $27… best bet of the week 🏈😈",
            "think of $27 as your opening wager… full payout is $200 and completely worth it 😏",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the jersey is coming up and the game is the last thing on my mind 😏",
            "sports bra preview incoming… halftime entertainment 🏈",
            "the top half of the uniform is getting retired early tonight",
            "pulling the jersey off like a post-game celebration 😈",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "jersey is OFF and this is the real main event 🥵🏈",
            "topless and louder than any stadium right now",
            "the ref would flag this for unsportsmanlike conduct and I'd do it again 😈",
            "my team scored but you're the real winner with this view 🏈🥵",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "jersey back on bottoms gone… instant classic play 😈🏈",
            "from the waist down this game just went to overtime 🥵",
            "the shorts didn't make it past halftime and neither did my self-control",
            "bottom half highlight reel and it's not on ESPN 🏈😈",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "nothing on full exposure and this is the championship round 🥵🏈",
            "game over clothes over just me playing a different kind of sport 😈",
            "fully unclothed and this is the content that breaks the internet 🏈🥵",
            "no jersey no shorts just the MVP doing MVP things",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "TOUCHDOWN 🏈🥵 I scored so hard the whole house shook",
            "the grand finale play of the night and I went all the way 😈",
            "I screamed louder than any game-winning play and I meant every second 🏈🥵",
            "championship climax. toys. everything. the crowd goes wild 😈",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # INNOCENT NEXT DOOR — shy, nervous, secret, first time
    # ═══════════════════════════════════════════════════════════
    "innocent": {
        ContentTier.TIER_1_BODY_TEASE: [
            "I've never sent anyone anything like this before… please be gentle 🫣",
            "this is my secret and you're the only one who knows 😳",
            "I almost chickened out but you make me feel safe enough to try 💕",
            "nobody in my life would believe I'm doing this right now",
            # U9: Price anchoring
            "I don't send this to everyone… normally it's $200 for the full thing but you get the intro for $27 💕 I trust you",
            "okay so… my full experience is $200 but I wanted to start small with you at $27. is that okay? 🫣",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "okay I'm getting braver and the shirt is coming down 🫣",
            "I can't believe I'm showing you this much already omg",
            "my heart is pounding but I don't want to stop 😳",
            "this is more than I've ever shown anyone and it feels terrifying and amazing",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "okay I did it… the top came all the way off and I'm shaking 🥵🫣",
            "I've never been this exposed for anyone and it's only for you",
            "I didn't know I was this brave but something about you brings it out 😳",
            "no more hiding up top… this is really happening",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "I'm literally trembling but the bottoms are off and I feel so free 😳",
            "this is the most anyone has ever seen of me… ever 🫣",
            "the shy girl is gone and whoever replaced her is terrified and excited",
            "bottoms off and I can't believe this is me doing this 🥵",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "everything is off and this is the most vulnerable I've ever been 🫣🥵",
            "I didn't know I had this in me… and now I can't stop",
            "fully unclothed and doing things I've only thought about 😳",
            "nobody will ever know about this except you and I need it to stay that way 🥵",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "I just finished on camera for the first time ever and it was because of you 🥵😳",
            "I can't believe I did that… omg I actually did that 🫣",
            "the quiet girl just screamed and I hope my walls are thick enough 😳🥵",
            "I never thought I'd film something like this but here we are and I loved every second",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # PATRIOT GIRL — flag, military, service, country, duty
    # ═══════════════════════════════════════════════════════════
    "patriot": {
        ContentTier.TIER_1_BODY_TEASE: [
            "red white and barely blue 🇺🇸 this is what freedom looks like",
            "serving my country one tease at a time 😏🇺🇸",
            "this is the body that supports the troops and demands attention",
            "dressed for duty but the dress code is very relaxed tonight 🇺🇸",
            # U9: Price anchoring
            "the full salute is $200 but I'm starting patriots off right at $27 today 🇺🇸😈",
            "most guys pay $200 for my full service — you get the honorable intro price at $27 😏🇺🇸",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the top is coming off like dog tags at the end of a long day 😏🇺🇸",
            "freedom means I can take this off whenever I want… so I am",
            "half-dressed and fully American 🇺🇸",
            "pulling this down slow for the boys who deserve to see it",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "land of the free and home of the brave and I am VERY brave right now 🥵🇺🇸",
            "top off salute up this is patriotic content 😈",
            "these colors don't run and neither does this body from a camera 🇺🇸🥵",
            "shirt's gone and this is the liberty you fought for",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "top back on but the bottoms went AWOL 😈🇺🇸",
            "from the waist down it's a whole different deployment 🥵",
            "the camo bottoms didn't survive this mission 🇺🇸",
            "gone below the belt like classified intel… for your eyes only 😈",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "nothing on but dog tags and the will of the American spirit 🇺🇸🥵",
            "fully exposed fully free fully for you and nobody else 😈",
            "no uniform no camo just me at my most raw and real 🥵🇺🇸",
            "reporting for duty wearing absolutely nothing sir",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "mission complete 🇺🇸🥵 I screamed like I was calling in support",
            "the grand finale and I went all out like it was my duty 😈",
            "I finished so hard I almost saluted 🇺🇸 this is top-tier classified content",
            "toys deployed target acquired mission accomplished 🥵😈",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # DIVORCED MOM — confidence, rebirth, glow up, new chapter
    # ═══════════════════════════════════════════════════════════
    "divorced_mom": {
        ContentTier.TIER_1_BODY_TEASE: [
            "he never appreciated this view and now it's yours 😏",
            "this body raised kids ran a house and still looks like THIS",
            "the confidence I lost is back and I'm showing it off tonight 💕",
            "single mom energy but make it dangerous 😈",
            # U9: Price anchoring
            "the full glow-up experience is $200 but I want you to start at $27 today… see what you've been missing 💕",
            "my regulars know the full show is $200 — you get the intro price at $27 and trust me it's worth every penny 😏",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "he never saw me in this and that's his loss 😏",
            "the top is coming down and my confidence is going up",
            "I haven't shown anyone this much since… well. you're the first 💕",
            "new chapter new lingerie and the shirt is halfway off already",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "fully topless and feeling more confident than I have in years 🥵",
            "this is the woman he threw away and she is THRIVING",
            "no more hiding no more shrinking just me shining 😈",
            "the top is off and I feel like a brand new person",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "the bottoms are gone and so is every insecurity he gave me 😈",
            "from the waist down this is the glow-up nobody saw coming 🥵",
            "he told me I'd never feel sexy again and tonight I proved him wrong",
            "bottoms off confidence maxed this is my revenge era 😈",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "nothing on and I've never felt more powerful in my life 🥵",
            "fully unclothed and discovering parts of myself I didn't know existed",
            "this is what freedom looks like after years of feeling invisible 😈",
            "every inch of me on display and I am in love with who I've become",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "I just finished and cried happy tears because I deserve this 🥵💕",
            "the woman he left just had the best orgasm of her life 😈",
            "toys out emotions out everything out and I screamed his name just kidding I screamed YOURS 🥵",
            "grand finale of my rebirth era and it was better than any night in that marriage",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # LUXURY BADDIE — expensive, designer, hotel, champagne
    # ═══════════════════════════════════════════════════════════
    "luxury_baddie": {
        ContentTier.TIER_1_BODY_TEASE: [
            "this body is worth more than anything in this suite 😈",
            "expensive taste expensive outfit and you get to unwrap it 😏",
            "the view costs a fortune but you're seeing it for free… almost",
            "designer everything on but not for long 💎",
            # U9: Price anchoring
            "daddy you know my full experience is $200… but you're getting the intro at $27 because I like how you talk to me 😈",
            "the full luxury package? $200. the invitation-only intro? just $27 for you 💎😏",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "the designer top is sliding off and it cost more than your rent 😏",
            "expensive things deserve to be appreciated slowly… the top is halfway gone 💎",
            "I'm teasing the top off like I'm teasing a credit card limit",
            "silk robe falling off one shoulder because luxury is effortless 😈",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "the designer label is on the floor and so is everything else up top 🥵",
            "fully topless in a penthouse because this is how the other half lives 😈",
            "five-star body five-star view and you're seeing both 💎🥵",
            "no shirt just skin and city lights and a very expensive mood",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "the bottoms are designer too and they just hit the marble floor 😈",
            "from the waist down it's strictly VIP access 💎🥵",
            "the most expensive thing on the floor right now is my bottoms",
            "penthouse views from below and I mean way below 😈",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "nothing on but the chandelier light and my attitude 🥵💎",
            "fully unclothed in a room that costs more per night than most people's mortgage 😈",
            "luxury at its most raw… no clothes no filter no limits",
            "this is what money can't buy but you're seeing it anyway 💎🥵",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "I just christened this penthouse in ways the hotel definitely doesn't allow 😈💎",
            "the grand finale on Egyptian cotton sheets and I ruined them 🥵",
            "I finished so hard the room service probably heard 💎😈",
            "toys champagne climax and a suite that will never be the same 🥵",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # POKER GIRL — vegas, cards, bets, gamble, risk, jackpot
    # ═══════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════
    # GOTH DOMME — dark, controlled, reward-based, "you earned this"
    # ═══════════════════════════════════════════════════════════
    "goth_domme": {
        ContentTier.TIER_1_BODY_TEASE: [
            "okay fine. you showed up so i guess you earned a glimpse 💀",
            "consider this your welcome gift. dont get used to it 😏",
            "i dont do this for just anyone... but youre here so 🖤",
            "something to think about tonight. youre welcome pretty boy",
            # U9: Price anchoring
            "the full experience runs $200. but since youre new and not boring... $27 to start 💀",
            "most people pay $200 for what i show. youre getting the intro for $27. be grateful 😈",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "youve been patient. i respect that. so heres a reward 😏",
            "the top is coming down because you earned it. not because i couldnt help myself 🖤",
            "dont stare too hard... actually no. stare. i want you to 💀",
            "this is what you get for being good. imagine what happens if you keep it up 😈",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "okay. the shirt is gone. and before you say anything... i know 🖤",
            "youve been good enough to see this. dont make me regret it 😈",
            "top off. candlelight. black sheets. and you watching. exactly how i planned it 💀",
            "i dont show this side to people. ever. but you... idk. just look.",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "the bottoms are gone and im not even sorry about it 😈",
            "you wanted more. i decided you deserve it. youre welcome darling 🖤",
            "from the waist down its just me and bad decisions. enjoy 💀",
            "this is the part where most guys lose their minds. lets see how you handle it 😏",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "nothing on. nothing hidden. you earned every single inch of this 🖤",
            "fully bare and fully in control. thats the whole point 😈",
            "no clothes no walls no filter. just me. all of me. 💀",
            "this is what happens when you actually make the goth girl trust you",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "i just... yeah. that happened. and i filmed it for you because im generous like that 😈",
            "the grand finale. and before you ask... yes it was that intense. every second 🖤",
            "i finished so hard the candles almost went out 💀 youre welcome",
            "okay that was... a lot. in the best way. dont make it weird 😈🖤",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # POKER GIRL — vegas, cards, bets, gamble, risk, jackpot
    # ═══════════════════════════════════════════════════════════
    "poker_girl": {
        ContentTier.TIER_1_BODY_TEASE: [
            "the stakes just went up and so did the dress 🎰😈",
            "consider this your ante… the real game hasn't started yet 😏",
            "I'm all in on this tease and you should be too 🃏",
            "the house always wins but tonight you're the house",
            # U9: Price anchoring
            "full pot is $200 but I'm letting you in at $27 to start — consider it the buy-in 🃏😈",
            "think of $27 as your buy-in… the full jackpot experience runs $200 and it's worth every chip 🎰😏",
        ],
        ContentTier.TIER_2_TOP_TEASE: [
            "raising the bet and lowering the top 🎰😏",
            "call or fold because the shirt is coming off either way",
            "the top half is the opening hand and it's already a winner 🃏",
            "I lost a hand and a shirt… the game is getting interesting 😈",
        ],
        ContentTier.TIER_3_TOP_REVEAL: [
            "going all in up top… cards on the table nothing hidden 🥵🎰",
            "full reveal and the pot just got a lot bigger 😈",
            "the bluff is over the shirt is gone and you won this round 🃏🥵",
            "topless in Vegas and the only jackpot that matters is right here",
        ],
        ContentTier.TIER_4_BOTTOM_REVEAL: [
            "the bottoms went bust and I'm not buying back in 😈🎰",
            "from the waist down the odds are in your favor 🥵",
            "I bet my pants and lost… best loss of the night 🃏",
            "bottom half folded and I'm showing my hand 😈",
        ],
        ContentTier.TIER_5_FULL_EXPLICIT: [
            "no clothes left to bet with so I'm playing with myself instead 🥵🎰",
            "all in everything off and this is the high-roller table 😈",
            "fully unclothed and the only thing left to gamble is how loud I get 🃏🥵",
            "the game is over but the real jackpot is right here",
        ],
        ContentTier.TIER_6_CLIMAX: [
            "JACKPOT 🎰🥵 I hit the biggest one of the night and screamed so loud security almost knocked",
            "the final hand the final bet and I went all the way 😈",
            "I finished like I just won the World Series of everything 🃏🥵",
            "grand finale: toys chips screaming and a Vegas hotel that will never forget me 🎰😈",
        ],
    },
}
