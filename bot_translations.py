"""
Massi-Bot — Bot Translations
==============================
All pre-education messages in every supported language.

Language codes follow the pattern:
  - "en"    → English
  - "es"    → Neutral Spanish (fallback for all Spanish variants)
  - "es-AR" → Argentine Spanish (voseo)
  - "pt-BR" → Brazilian Portuguese

To add a new language:
  1. Copy STEPS_EN
  2. Translate every "text" and "button" value
  3. Add to STEPS dict at the bottom
  4. Add acknowledgment to ACK_MSG
  5. Add label to LANG_LABELS

The bot resolves locale → translation:
  "es-CO" → tries STEPS["es-CO"], falls back to STEPS["es"]
  "es-AR" → tries STEPS["es-AR"], finds it (voseo version)
  "pt-BR" → tries STEPS["pt-BR"], finds it
"""


# ═══════════════════════════════════════════════════════════════
# ENGLISH
# ═══════════════════════════════════════════════════════════════

STEPS_EN = [
    {
        "text": (
            "Hey! 👋\n\n"
            "Welcome — I'm so glad you applied. This is where everything starts.\n\n"
            "Before our call, I want to walk you through exactly how this works "
            "so when we talk, we can skip the basics and get straight to setting you up.\n\n"
            "Tap the button below whenever you're ready for the next section. "
            "Take your time — there's no rush."
        ),
        "button": "Let's Go →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  HOW THE AGENCY WORKS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Here's the deal — your only job is to make content. That's it.\n\n"
            "Everything else — the chatting with subscribers, the social media strategy, "
            "the Instagram accounts, the taxes, the business side — that's all on me.\n\n"
            "I don't take a single dollar from you upfront. Not now, not ever. "
            "We use a 60/40 revenue split: 60% to the agency, 40% to you. "
            "Every dollar is tracked automatically through a third-party platform "
            "called Melon — you can see every transaction in real time.\n\n"
            "We only eat when you eat. That's how it works."
        ),
        "button": "Next →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  YOUR CONTENT — WHAT YOU ACTUALLY DO\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "The content system is built so you do less work and make more money.\n\n"
            "You'll shoot content across 6 tiers — from fully clothed tease shots "
            "all the way to exclusive premium content. Each tier is priced strategically "
            "so subscribers naturally move up in spend.\n\n"
            "For social media, you shoot once in a skin-tight outfit (no skin showing) "
            "and our AI system handles the rest — putting you in different outfits, "
            "synced to your voice, at professional quality.\n\n"
            "You don't need to be a photographer. You don't need expensive equipment. "
            "A phone and good lighting is all it takes to start."
        ),
        "button": "Next →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  THE CHATTING SYSTEM — YOU NEVER TALK TO THEM\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "This is the part everyone asks about — \"do I have to talk to these guys?\"\n\n"
            "No. Not once. Never.\n\n"
            "We built a proprietary AI chatting engine that handles every conversation "
            "24 hours a day, 7 days a week. It uses psychologically-driven scripts "
            "to build real connection with subscribers and move them through a "
            "6-tier closing system.\n\n"
            "Each of your Instagram accounts feeds into its own AI persona — "
            "with its own voice, its own personality, and its own strategy for converting.\n\n"
            "You never see the messages. You never deal with the back and forth. "
            "Money comes in, your 40% hits your account. That's it."
        ),
        "button": "Next →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  THE MULTI-PLATFORM STRATEGY\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Here's what separates us from everyone else.\n\n"
            "One Instagram account is not enough. The women making serious money "
            "are running up to 10 accounts simultaneously — each one targeting "
            "a different niche audience.\n\n"
            "We build and manage ALL of them for you. Each account has its own "
            "aesthetic, its own growth strategy, and its own funnel feeding "
            "subscribers into your page.\n\n"
            "10 traffic sources instead of 1. That's not a small difference — "
            "that's the difference between a $2K month and a $20K month."
        ),
        "button": "Next →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  YOUR MONEY & YOUR PROTECTION\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Let me be completely transparent about the money.\n\n"
            "We use Melon (getmelon.io) — a third-party revenue-share platform "
            "trusted by 125+ agencies. The moment your earnings hit, Melon "
            "automatically triggers the 60/40 split. Your 40% goes directly to you. "
            "No manual transfers. No awkward conversations.\n\n"
            "On top of that, everything is documented in a signed contract before "
            "we start. Your earnings, your rights, our responsibilities — all in writing.\n\n"
            "There's never a question about money because the system handles it "
            "automatically and the contract backs it up."
        ),
        "button": "Next →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  YOUR 90-DAY ROADMAP\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Here's what the first 90 days look like:\n\n"
            "📅 Week 1 — Onboarding. You sign the contract, connect to Melon, "
            "fill out your profile, and start shooting your first content.\n\n"
            "📅 Weeks 2-4 — Accounts go live. Your Instagram accounts start growing, "
            "the chatting system activates, and subscribers start coming in.\n\n"
            "📅 Month 2 — Momentum. Real revenue is hitting your account. "
            "We double down on what's working.\n\n"
            "📅 Month 3 — Scale. The goal is $10,000/month by day 90. "
            "We've done it before and we'll do it with you."
        ),
        "button": "Next →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  YOU'RE ALL CAUGHT UP\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "That's everything you need to know before our call.\n\n"
            "When we get on the phone, we're not going to repeat any of this. "
            "Instead, we'll get you set up — connect your accounts, build your profile, "
            "and map out your first two weeks of content.\n\n"
            "If you have any questions before the call, just type them here "
            "and I'll get back to you.\n\n"
            "Talk soon 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# NEUTRAL SPANISH (tuteo — Colombia, Mexico, Peru, Chile, etc.)
# ═══════════════════════════════════════════════════════════════

STEPS_ES = [
    {
        "text": (
            "¡Hola! 👋\n\n"
            "Bienvenida — me alegra mucho que hayas aplicado. Aquí es donde todo comienza.\n\n"
            "Antes de nuestra llamada, quiero explicarte exactamente cómo funciona todo "
            "para que cuando hablemos, podamos saltarnos lo básico e ir directo a configurar todo.\n\n"
            "Toca el botón de abajo cuando estés lista para la siguiente sección. "
            "Tómate tu tiempo — no hay prisa."
        ),
        "button": "Empezar →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  CÓMO FUNCIONA LA AGENCIA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "El acuerdo es simple — tu único trabajo es crear contenido. Eso es todo.\n\n"
            "Todo lo demás — el chat con los suscriptores, la estrategia de redes sociales, "
            "las cuentas de Instagram, los impuestos, la parte del negocio — todo eso es mi responsabilidad.\n\n"
            "No te cobro ni un solo dólar por adelantado. Ni ahora, ni nunca. "
            "Usamos un reparto de ingresos 60/40: 60% para la agencia, 40% para ti. "
            "Cada dólar se rastrea automáticamente a través de una plataforma de terceros "
            "llamada Melon — puedes ver cada transacción en tiempo real.\n\n"
            "Solo ganamos cuando tú ganas. Así de simple."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  TU CONTENIDO — LO QUE REALMENTE HACES\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "El sistema de contenido está diseñado para que trabajes menos y ganes más.\n\n"
            "Vas a grabar contenido en 6 niveles — desde fotos con ropa completa "
            "hasta contenido premium exclusivo. Cada nivel tiene un precio estratégico "
            "para que los suscriptores naturalmente gasten más.\n\n"
            "Para las redes sociales, grabas una vez con ropa ajustada (sin mostrar piel) "
            "y nuestro sistema de IA se encarga del resto — poniéndote en diferentes outfits, "
            "sincronizado con tu voz, con calidad profesional.\n\n"
            "No necesitas ser fotógrafa. No necesitas equipo caro. "
            "Un teléfono y buena iluminación es todo lo que necesitas para empezar."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  EL SISTEMA DE CHAT — TÚ NUNCA HABLAS CON ELLOS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Esta es la parte que todas preguntan — \"¿tengo que hablar con estos tipos?\"\n\n"
            "No. Ni una vez. Nunca.\n\n"
            "Construimos un motor de chat con inteligencia artificial que maneja cada "
            "conversación las 24 horas del día, los 7 días de la semana. Usa guiones "
            "psicológicamente diseñados para crear conexión real con los suscriptores "
            "y llevarlos a través de un sistema de cierre de 6 niveles.\n\n"
            "Cada una de tus cuentas de Instagram alimenta su propia persona de IA — "
            "con su propia voz, su propia personalidad y su propia estrategia para convertir.\n\n"
            "Tú nunca ves los mensajes. Nunca lidias con eso. "
            "El dinero entra, tu 40% llega a tu cuenta. Así de fácil."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  LA ESTRATEGIA MULTI-PLATAFORMA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Esto es lo que nos separa de todos los demás.\n\n"
            "Una cuenta de Instagram no es suficiente. Las mujeres que ganan en serio "
            "manejan hasta 10 cuentas simultáneamente — cada una dirigida a un "
            "público diferente.\n\n"
            "Nosotros construimos y manejamos TODAS para ti. Cada cuenta tiene su propia "
            "estética, su propia estrategia de crecimiento y su propio embudo que lleva "
            "suscriptores a tu página.\n\n"
            "10 fuentes de tráfico en lugar de 1. Esa no es una pequeña diferencia — "
            "es la diferencia entre un mes de $2,000 y un mes de $20,000."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  TU DINERO Y TU PROTECCIÓN\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Déjame ser completamente transparente sobre el dinero.\n\n"
            "Usamos Melon (getmelon.io) — una plataforma de reparto de ingresos "
            "de terceros en la que confían más de 125 agencias. En el momento en que "
            "llegan tus ganancias, Melon automáticamente activa el reparto 60/40. "
            "Tu 40% va directamente a ti. Sin transferencias manuales. Sin conversaciones incómodas.\n\n"
            "Además de eso, todo está documentado en un contrato firmado antes de empezar. "
            "Tus ganancias, tus derechos, nuestras responsabilidades — todo por escrito.\n\n"
            "Nunca hay una pregunta sobre el dinero porque el sistema lo maneja "
            "automáticamente y el contrato lo respalda."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  TU PLAN DE 90 DÍAS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Así se ven los primeros 90 días:\n\n"
            "📅 Semana 1 — Onboarding. Firmas el contrato, te conectas a Melon, "
            "llenas tu perfil y empiezas a grabar tu primer contenido.\n\n"
            "📅 Semanas 2-4 — Las cuentas se activan. Tus cuentas de Instagram empiezan a crecer, "
            "el sistema de chat se activa y los suscriptores empiezan a llegar.\n\n"
            "📅 Mes 2 — Impulso. El dinero real está llegando a tu cuenta. "
            "Duplicamos lo que está funcionando.\n\n"
            "📅 Mes 3 — Escalar. La meta es $10,000/mes para el día 90. "
            "Lo hemos logrado antes y lo haremos contigo."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  YA ESTÁS AL DÍA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Eso es todo lo que necesitas saber antes de nuestra llamada.\n\n"
            "Cuando hablemos por teléfono, no vamos a repetir nada de esto. "
            "En su lugar, vamos a configurar todo — conectar tus cuentas, crear tu perfil "
            "y planificar tus primeras dos semanas de contenido.\n\n"
            "Si tienes alguna pregunta antes de la llamada, simplemente escríbela aquí "
            "y te responderé.\n\n"
            "Hablamos pronto 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# ARGENTINE SPANISH (voseo — Argentina, Uruguay)
# ═══════════════════════════════════════════════════════════════

STEPS_ES_AR = [
    {
        "text": (
            "¡Hola! 👋\n\n"
            "Bienvenida — me alegra mucho que hayas aplicado. Acá es donde todo empieza.\n\n"
            "Antes de nuestra llamada, quiero explicarte exactamente cómo funciona todo "
            "para que cuando hablemos, podamos saltarnos lo básico e ir directo a configurar todo.\n\n"
            "Tocá el botón de abajo cuando estés lista para la siguiente sección. "
            "Tomate tu tiempo — no hay apuro."
        ),
        "button": "Empezar →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  CÓMO FUNCIONA LA AGENCIA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "El acuerdo es simple — tu único trabajo es crear contenido. Eso es todo.\n\n"
            "Todo lo demás — el chat con los suscriptores, la estrategia de redes sociales, "
            "las cuentas de Instagram, los impuestos, la parte del negocio — todo eso es mi responsabilidad.\n\n"
            "No te cobro ni un solo dólar por adelantado. Ni ahora, ni nunca. "
            "Usamos un reparto de ingresos 60/40: 60% para la agencia, 40% para vos. "
            "Cada dólar se rastrea automáticamente a través de una plataforma de terceros "
            "llamada Melon — podés ver cada transacción en tiempo real.\n\n"
            "Solo ganamos cuando vos ganás. Así de simple."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  TU CONTENIDO — LO QUE REALMENTE HACÉS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "El sistema de contenido está diseñado para que trabajes menos y ganes más.\n\n"
            "Vas a grabar contenido en 6 niveles — desde fotos con ropa completa "
            "hasta contenido premium exclusivo. Cada nivel tiene un precio estratégico "
            "para que los suscriptores naturalmente gasten más.\n\n"
            "Para las redes sociales, grabás una vez con ropa ajustada (sin mostrar piel) "
            "y nuestro sistema de IA se encarga del resto — poniéndote en diferentes outfits, "
            "sincronizado con tu voz, con calidad profesional.\n\n"
            "No necesitás ser fotógrafa. No necesitás equipo caro. "
            "Un teléfono y buena iluminación es todo lo que necesitás para empezar."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  EL SISTEMA DE CHAT — VOS NUNCA HABLÁS CON ELLOS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Esta es la parte que todas preguntan — \"¿tengo que hablar con estos tipos?\"\n\n"
            "No. Ni una vez. Nunca.\n\n"
            "Construimos un motor de chat con inteligencia artificial que maneja cada "
            "conversación las 24 horas del día, los 7 días de la semana. Usa guiones "
            "psicológicamente diseñados para crear conexión real con los suscriptores "
            "y llevarlos a través de un sistema de cierre de 6 niveles.\n\n"
            "Cada una de tus cuentas de Instagram alimenta su propia persona de IA — "
            "con su propia voz, su propia personalidad y su propia estrategia para convertir.\n\n"
            "Vos nunca ves los mensajes. Nunca lidiás con eso. "
            "La plata entra, tu 40% llega a tu cuenta. Así de fácil."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  LA ESTRATEGIA MULTI-PLATAFORMA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Esto es lo que nos separa de todos los demás.\n\n"
            "Una cuenta de Instagram no alcanza. Las mujeres que ganan en serio "
            "manejan hasta 10 cuentas simultáneamente — cada una dirigida a un "
            "público diferente.\n\n"
            "Nosotros construimos y manejamos TODAS para vos. Cada cuenta tiene su propia "
            "estética, su propia estrategia de crecimiento y su propio embudo que lleva "
            "suscriptores a tu página.\n\n"
            "10 fuentes de tráfico en lugar de 1. Esa no es una diferencia chica — "
            "es la diferencia entre un mes de $2,000 y un mes de $20,000."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  TU PLATA Y TU PROTECCIÓN\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Dejame ser completamente transparente sobre la plata.\n\n"
            "Usamos Melon (getmelon.io) — una plataforma de reparto de ingresos "
            "de terceros en la que confían más de 125 agencias. En el momento en que "
            "llegan tus ganancias, Melon automáticamente activa el reparto 60/40. "
            "Tu 40% va directamente a vos. Sin transferencias manuales. Sin conversaciones incómodas.\n\n"
            "Además de eso, todo está documentado en un contrato firmado antes de empezar. "
            "Tus ganancias, tus derechos, nuestras responsabilidades — todo por escrito.\n\n"
            "Nunca hay una pregunta sobre la plata porque el sistema lo maneja "
            "automáticamente y el contrato lo respalda."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  TU PLAN DE 90 DÍAS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Así se ven los primeros 90 días:\n\n"
            "📅 Semana 1 — Onboarding. Firmás el contrato, te conectás a Melon, "
            "llenás tu perfil y empezás a grabar tu primer contenido.\n\n"
            "📅 Semanas 2-4 — Las cuentas se activan. Tus cuentas de Instagram empiezan a crecer, "
            "el sistema de chat se activa y los suscriptores empiezan a llegar.\n\n"
            "📅 Mes 2 — Impulso. La plata real está llegando a tu cuenta. "
            "Duplicamos lo que está funcionando.\n\n"
            "📅 Mes 3 — Escalar. La meta es $10,000/mes para el día 90. "
            "Lo logramos antes y lo vamos a hacer con vos."
        ),
        "button": "Siguiente →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  YA ESTÁS AL DÍA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Eso es todo lo que necesitás saber antes de nuestra llamada.\n\n"
            "Cuando hablemos por teléfono, no vamos a repetir nada de esto. "
            "En su lugar, vamos a configurar todo — conectar tus cuentas, crear tu perfil "
            "y planificar tus primeras dos semanas de contenido.\n\n"
            "Si tenés alguna pregunta antes de la llamada, simplemente escribila acá "
            "y te respondo.\n\n"
            "Hablamos pronto 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# BRAZILIAN PORTUGUESE
# ═══════════════════════════════════════════════════════════════

STEPS_PT_BR = [
    {
        "text": (
            "Oi! 👋\n\n"
            "Bem-vinda — fico muito feliz que você se inscreveu. É aqui que tudo começa.\n\n"
            "Antes da nossa ligação, quero te explicar exatamente como tudo funciona "
            "para que quando a gente conversar, possamos pular o básico e ir direto à configuração.\n\n"
            "Toque no botão abaixo quando estiver pronta para a próxima seção. "
            "Vá no seu ritmo — sem pressa."
        ),
        "button": "Vamos lá →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  COMO A AGÊNCIA FUNCIONA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "O acordo é simples — seu único trabalho é criar conteúdo. Só isso.\n\n"
            "Todo o resto — o chat com assinantes, a estratégia de redes sociais, "
            "as contas do Instagram, os impostos, a parte do negócio — tudo isso é minha responsabilidade.\n\n"
            "Eu não cobro nenhum centavo antecipado. Nem agora, nem nunca. "
            "Usamos uma divisão de receita 60/40: 60% para a agência, 40% para você. "
            "Cada real é rastreado automaticamente através de uma plataforma terceirizada "
            "chamada Melon — você pode ver cada transação em tempo real.\n\n"
            "Só ganhamos quando você ganha. Simples assim."
        ),
        "button": "Próximo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  SEU CONTEÚDO — O QUE VOCÊ REALMENTE FAZ\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "O sistema de conteúdo foi feito para que você trabalhe menos e ganhe mais.\n\n"
            "Você vai gravar conteúdo em 6 níveis — desde fotos com roupa completa "
            "até conteúdo premium exclusivo. Cada nível tem um preço estratégico "
            "para que os assinantes naturalmente gastem mais.\n\n"
            "Para as redes sociais, você grava uma vez com roupa justa (sem mostrar pele) "
            "e nosso sistema de IA cuida do resto — colocando você em diferentes looks, "
            "sincronizado com sua voz, com qualidade profissional.\n\n"
            "Você não precisa ser fotógrafa. Não precisa de equipamento caro. "
            "Um celular e boa iluminação é tudo que você precisa para começar."
        ),
        "button": "Próximo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  O SISTEMA DE CHAT — VOCÊ NUNCA FALA COM ELES\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Essa é a parte que todo mundo pergunta — \"eu tenho que falar com esses caras?\"\n\n"
            "Não. Nem uma vez. Nunca.\n\n"
            "Construímos um motor de chat com inteligência artificial que gerencia cada "
            "conversa 24 horas por dia, 7 dias por semana. Usa roteiros "
            "psicologicamente projetados para criar conexão real com os assinantes "
            "e levá-los através de um sistema de fechamento de 6 níveis.\n\n"
            "Cada uma das suas contas do Instagram alimenta sua própria persona de IA — "
            "com sua própria voz, sua própria personalidade e sua própria estratégia de conversão.\n\n"
            "Você nunca vê as mensagens. Nunca lida com isso. "
            "O dinheiro entra, seus 40% caem na sua conta. Simples assim."
        ),
        "button": "Próximo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  A ESTRATÉGIA MULTI-PLATAFORMA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Isso é o que nos separa de todos os outros.\n\n"
            "Uma conta de Instagram não é suficiente. As mulheres que ganham de verdade "
            "gerenciam até 10 contas simultaneamente — cada uma direcionada a um "
            "público diferente.\n\n"
            "Nós construímos e gerenciamos TODAS para você. Cada conta tem sua própria "
            "estética, sua própria estratégia de crescimento e seu próprio funil que leva "
            "assinantes para sua página.\n\n"
            "10 fontes de tráfego em vez de 1. Essa não é uma diferença pequena — "
            "é a diferença entre um mês de $2.000 e um mês de $20.000."
        ),
        "button": "Próximo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  SEU DINHEIRO E SUA PROTEÇÃO\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Deixa eu ser completamente transparente sobre o dinheiro.\n\n"
            "Usamos a Melon (getmelon.io) — uma plataforma terceirizada de divisão de receita "
            "usada por mais de 125 agências. No momento em que seus ganhos chegam, "
            "a Melon automaticamente ativa a divisão 60/40. "
            "Seus 40% vão direto para você. Sem transferências manuais. Sem conversas chatas.\n\n"
            "Além disso, tudo é documentado em um contrato assinado antes de começar. "
            "Seus ganhos, seus direitos, nossas responsabilidades — tudo por escrito.\n\n"
            "Nunca há dúvida sobre o dinheiro porque o sistema cuida de tudo "
            "automaticamente e o contrato garante."
        ),
        "button": "Próximo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  SEU PLANO DE 90 DIAS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Assim são os primeiros 90 dias:\n\n"
            "📅 Semana 1 — Onboarding. Você assina o contrato, se conecta ao Melon, "
            "preenche seu perfil e começa a gravar seu primeiro conteúdo.\n\n"
            "📅 Semanas 2-4 — As contas vão ao ar. Suas contas do Instagram começam a crescer, "
            "o sistema de chat é ativado e os assinantes começam a chegar.\n\n"
            "📅 Mês 2 — Impulso. Dinheiro real está chegando na sua conta. "
            "Dobramos a aposta no que está funcionando.\n\n"
            "📅 Mês 3 — Escalar. A meta é $10.000/mês até o dia 90. "
            "Já conseguimos antes e vamos conseguir com você."
        ),
        "button": "Próximo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  VOCÊ ESTÁ POR DENTRO DE TUDO\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Isso é tudo que você precisa saber antes da nossa ligação.\n\n"
            "Quando a gente falar por telefone, não vamos repetir nada disso. "
            "Em vez disso, vamos configurar tudo — conectar suas contas, criar seu perfil "
            "e planejar suas primeiras duas semanas de conteúdo.\n\n"
            "Se você tiver alguma pergunta antes da ligação, é só digitar aqui "
            "que eu te respondo.\n\n"
            "Falamos em breve 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# FRENCH
# ═══════════════════════════════════════════════════════════════

STEPS_FR = [
    {
        "text": (
            "Salut ! 👋\n\n"
            "Bienvenue — je suis vraiment contente que tu aies postulé. C'est ici que tout commence.\n\n"
            "Avant notre appel, je veux t'expliquer exactement comment ça fonctionne "
            "pour qu'on puisse aller droit au but sans perdre de temps sur les bases.\n\n"
            "Appuie sur le bouton ci-dessous quand tu es prête pour la section suivante. "
            "Prends ton temps — rien ne presse."
        ),
        "button": "C'est parti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  COMMENT FONCTIONNE L'AGENCE\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Voilà l'accord — ton seul travail, c'est de créer du contenu. C'est tout.\n\n"
            "Tout le reste — les chats avec les abonnés, la stratégie sur les réseaux sociaux, "
            "les comptes Instagram, la comptabilité, la partie business — tout ça c'est moi qui m'en occupe.\n\n"
            "Je ne te prends pas un seul euro à l'avance. Jamais. "
            "On utilise un partage des revenus 60/40 : 60% pour l'agence, 40% pour toi. "
            "Chaque euro est suivi automatiquement via une plateforme tierce appelée Melon — "
            "tu vois chaque transaction en temps réel.\n\n"
            "On gagne seulement quand tu gagnes. C'est comme ça que ça marche."
        ),
        "button": "Suivant →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  TON CONTENU — CE QUE TU FAIS VRAIMENT\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Le système de contenu est conçu pour que tu travailles moins et gagnes plus.\n\n"
            "Tu vas filmer du contenu sur 6 niveaux — des photos habillées sexy "
            "jusqu'au contenu premium exclusif. Chaque niveau est tarifé de façon stratégique "
            "pour que les abonnés dépensent naturellement de plus en plus.\n\n"
            "Pour les réseaux sociaux, tu te filmes une fois en tenue moulante (sans montrer de peau) "
            "et notre système IA s'occupe du reste — en te mettant dans différentes tenues, "
            "synchronisé avec ta voix, à qualité professionnelle.\n\n"
            "Tu n'as pas besoin d'être photographe. Tu n'as pas besoin d'équipement coûteux. "
            "Un téléphone et un bon éclairage suffisent pour commencer."
        ),
        "button": "Suivant →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  LE SYSTÈME DE CHAT — TU NE LEUR PARLES JAMAIS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "C'est la question que tout le monde pose — \"est-ce que je dois parler à ces gars ?\"\n\n"
            "Non. Pas une seule fois. Jamais.\n\n"
            "On a créé un moteur de messagerie IA propriétaire qui gère chaque conversation "
            "24h/24, 7j/7. Il utilise des scripts basés sur la psychologie "
            "pour créer une vraie connexion avec les abonnés et les faire progresser dans "
            "un système de vente sur 6 niveaux.\n\n"
            "Chacun de tes comptes Instagram alimente son propre persona IA — "
            "avec sa voix, sa personnalité et sa stratégie de conversion propres.\n\n"
            "Tu ne vois jamais les messages. Tu ne t'occupes jamais des échanges. "
            "L'argent rentre, ton 40% arrive sur ton compte. C'est tout."
        ),
        "button": "Suivant →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  LA STRATÉGIE MULTI-PLATEFORME\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Voilà ce qui nous différencie de tout le monde.\n\n"
            "Un seul compte Instagram, ce n'est pas suffisant. Les femmes qui gagnent sérieusement "
            "gèrent jusqu'à 10 comptes simultanément — chacun ciblant "
            "une niche d'audience différente.\n\n"
            "On les construit et les gère TOUS pour toi. Chaque compte a son propre "
            "univers visuel, sa stratégie de croissance et son tunnel qui "
            "amène des abonnés vers ta page.\n\n"
            "10 sources de trafic au lieu d'une seule. Ce n'est pas une petite différence — "
            "c'est la différence entre 2 000 € par mois et 20 000 € par mois."
        ),
        "button": "Suivant →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  TON ARGENT ET TA PROTECTION\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Soyons complètement transparents sur l'argent.\n\n"
            "On utilise Melon (getmelon.io) — une plateforme de partage de revenus tierce "
            "utilisée par plus de 125 agences. Dès que tes gains arrivent, Melon "
            "déclenche automatiquement le partage 60/40. Ton 40% va directement chez toi. "
            "Aucun virement manuel. Aucune conversation gênante.\n\n"
            "En plus de ça, tout est documenté dans un contrat signé avant "
            "de commencer. Tes revenus, tes droits, nos responsabilités — tout par écrit.\n\n"
            "Il n'y a jamais de question sur l'argent parce que le système le gère "
            "automatiquement et le contrat le garantit."
        ),
        "button": "Suivant →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  TA FEUILLE DE ROUTE SUR 90 JOURS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Voilà à quoi ressemblent les 90 premiers jours :\n\n"
            "📅 Semaine 1 — Onboarding. Tu signes le contrat, tu te connectes à Melon, "
            "tu remplis ton profil et tu commences à filmer tes premiers contenus.\n\n"
            "📅 Semaines 2-4 — Les comptes se lancent. Tes comptes Instagram commencent à grossir, "
            "le système de chat s'active et les abonnés arrivent.\n\n"
            "📅 Mois 2 — Momentum. De vrais revenus arrivent sur ton compte. "
            "On double la mise sur ce qui fonctionne.\n\n"
            "📅 Mois 3 — Scale. L'objectif est 10 000 €/mois au jour 90. "
            "On l'a déjà fait et on le fera avec toi."
        ),
        "button": "Suivant →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  TU ES PRÊTE\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "C'est tout ce que tu dois savoir avant notre appel.\n\n"
            "Quand on se parle, on ne va pas répéter tout ça. "
            "À la place, on va te configurer — connecter tes comptes, construire ton profil "
            "et planifier tes deux premières semaines de contenu.\n\n"
            "Si tu as des questions avant l'appel, écris-les ici "
            "et je te répondrai.\n\n"
            "À très vite 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# GERMAN
# ═══════════════════════════════════════════════════════════════

STEPS_DE = [
    {
        "text": (
            "Hey! 👋\n\n"
            "Willkommen — ich freue mich sehr, dass du dich beworben hast. Hier fängt alles an.\n\n"
            "Vor unserem Gespräch möchte ich dir genau erklären, wie das funktioniert, "
            "damit wir beim Anruf direkt loslegen können, ohne die Basics durchzugehen.\n\n"
            "Tippe auf den Button, wenn du für den nächsten Abschnitt bereit bist. "
            "Nimm dir Zeit — es gibt keinen Stress."
        ),
        "button": "Los geht's →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  WIE DIE AGENTUR FUNKTIONIERT\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "So läuft das — dein einziger Job ist es, Content zu erstellen. Das ist alles.\n\n"
            "Alles andere — das Chatten mit Abonnenten, die Social-Media-Strategie, "
            "die Instagram-Accounts, die Steuern, das Business — das übernehme alles ich.\n\n"
            "Ich nehme keinen einzigen Euro von dir im Voraus. Nie. "
            "Wir nutzen eine 60/40-Umsatzbeteiligung: 60% für die Agentur, 40% für dich. "
            "Jeder Euro wird automatisch über eine Drittanbieter-Plattform namens Melon verfolgt — "
            "du siehst jede Transaktion in Echtzeit.\n\n"
            "Wir verdienen nur, wenn du verdienst. So einfach ist das."
        ),
        "button": "Weiter →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  DEIN CONTENT — WAS DU WIRKLICH TUSt\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Das Content-System ist so aufgebaut, dass du weniger arbeitest und mehr verdienst.\n\n"
            "Du erstellst Content in 6 Stufen — von vollbekleideten Tease-Aufnahmen "
            "bis zu exklusivem Premium-Content. Jede Stufe ist strategisch bepreist, "
            "damit Abonnenten ganz natürlich mehr ausgeben.\n\n"
            "Für Social Media nimmst du dich einmal in enganliegender Kleidung auf (keine Haut zu sehen) "
            "und unser KI-System erledigt den Rest — es zieht dir verschiedene Outfits an, "
            "synchronisiert mit deiner Stimme, in Profiqualität.\n\n"
            "Du musst kein Fotograf sein. Du brauchst keine teure Ausrüstung. "
            "Ein Telefon und gutes Licht reichen zum Start."
        ),
        "button": "Weiter →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  DAS CHAT-SYSTEM — DU REDEST NIE MIT IHNEN\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Das ist die Frage, die alle stellen — \"muss ich wirklich mit diesen Typen reden?\"\n\n"
            "Nein. Kein einziges Mal. Niemals.\n\n"
            "Wir haben eine proprietäre KI-gestützte Messaging-Engine entwickelt, die jedes Gespräch "
            "24 Stunden am Tag, 7 Tage die Woche übernimmt. Sie nutzt psychologisch fundierte Skripte, "
            "um echte Verbindungen mit Abonnenten aufzubauen und sie durch ein "
            "6-stufiges Verkaufssystem zu führen.\n\n"
            "Jeder deiner Instagram-Accounts speist sein eigenes KI-Persona — "
            "mit eigener Stimme, eigener Persönlichkeit und eigener Konversionsstrategie.\n\n"
            "Du siehst nie die Nachrichten. Du kümmerst dich nie um den Austausch. "
            "Geld kommt rein, deine 40% landen auf deinem Konto. Das war's."
        ),
        "button": "Weiter →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  DIE MULTI-PLATTFORM-STRATEGIE\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Das ist es, was uns von allen anderen unterscheidet.\n\n"
            "Ein einziger Instagram-Account reicht nicht. Die Frauen, die wirklich viel verdienen, "
            "betreiben bis zu 10 Accounts gleichzeitig — jeder davon zielt auf "
            "eine andere Nischen-Zielgruppe ab.\n\n"
            "Wir bauen und managen sie ALLE für dich. Jeder Account hat sein eigenes "
            "Erscheinungsbild, seine eigene Wachstumsstrategie und seinen eigenen Funnel, "
            "der Abonnenten auf deine Seite bringt.\n\n"
            "10 Traffic-Quellen statt einer. Das ist kein kleiner Unterschied — "
            "das ist der Unterschied zwischen 2.000 € im Monat und 20.000 € im Monat."
        ),
        "button": "Weiter →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  DEIN GELD UND DEIN SCHUTZ\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Ich möchte vollkommen transparent beim Thema Geld sein.\n\n"
            "Wir nutzen Melon (getmelon.io) — eine Drittanbieter-Plattform für Umsatzbeteiligungen, "
            "der über 125 Agenturen vertrauen. Sobald deine Einnahmen eingehen, löst Melon "
            "automatisch die 60/40-Aufteilung aus. Deine 40% gehen direkt an dich. "
            "Keine manuellen Überweisungen. Kein unangenehmes Gespräch.\n\n"
            "Zusätzlich wird alles in einem unterzeichneten Vertrag festgehalten, bevor "
            "wir starten. Deine Einnahmen, deine Rechte, unsere Verantwortlichkeiten — alles schriftlich.\n\n"
            "Es gibt nie Fragen über Geld, weil das System es automatisch regelt "
            "und der Vertrag es absichert."
        ),
        "button": "Weiter →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  DEIN 90-TAGE-FAHRPLAN\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "So sehen die ersten 90 Tage aus:\n\n"
            "📅 Woche 1 — Onboarding. Du unterschreibst den Vertrag, verbindest dich mit Melon, "
            "füllst dein Profil aus und beginnst mit deinem ersten Content.\n\n"
            "📅 Wochen 2-4 — Accounts gehen live. Deine Instagram-Accounts wachsen, "
            "das Chat-System aktiviert sich und Abonnenten kommen rein.\n\n"
            "📅 Monat 2 — Momentum. Echtes Geld kommt auf dein Konto. "
            "Wir verdoppeln das, was funktioniert.\n\n"
            "📅 Monat 3 — Scale. Das Ziel sind 10.000 € im Monat an Tag 90. "
            "Wir haben das schon geschafft und werden es mit dir schaffen."
        ),
        "button": "Weiter →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  DU BIST BEREIT\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Das ist alles, was du vor unserem Gespräch wissen musst.\n\n"
            "Wenn wir telefonieren, wiederholen wir nichts davon. "
            "Stattdessen richten wir dich ein — verbinden deine Accounts, erstellen dein Profil "
            "und planen deine ersten zwei Wochen Content.\n\n"
            "Wenn du vor dem Anruf Fragen hast, schreib sie hier "
            "und ich melde mich bei dir.\n\n"
            "Bis gleich 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# ITALIAN
# ═══════════════════════════════════════════════════════════════

STEPS_IT = [
    {
        "text": (
            "Ciao! 👋\n\n"
            "Benvenuta — sono così contenta che tu abbia fatto domanda. Da qui inizia tutto.\n\n"
            "Prima della nostra chiamata, voglio spiegarti esattamente come funziona "
            "così quando parliamo possiamo saltare le basi e andare dritti alla configurazione.\n\n"
            "Premi il pulsante qui sotto quando sei pronta per la sezione successiva. "
            "Prenditi il tuo tempo — non c'è fretta."
        ),
        "button": "Iniziamo →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣  COME FUNZIONA L'AGENZIA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "L'accordo è semplice — il tuo unico lavoro è creare contenuti. Tutto qua.\n\n"
            "Tutto il resto — le chat con gli abbonati, la strategia sui social media, "
            "gli account Instagram, le tasse, la parte business — me ne occupo io.\n\n"
            "Non ti chiedo un solo euro in anticipo. Mai. "
            "Usiamo una divisione delle entrate 60/40: 60% all'agenzia, 40% a te. "
            "Ogni euro viene tracciato automaticamente tramite una piattaforma di terze parti "
            "chiamata Melon — puoi vedere ogni transazione in tempo reale.\n\n"
            "Guadagniamo solo quando guadagni tu. Funziona così."
        ),
        "button": "Avanti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "2️⃣  I TUOI CONTENUTI — COSA FAI DAVVERO\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Il sistema dei contenuti è costruito per farti lavorare meno e guadagnare di più.\n\n"
            "Girerai contenuti su 6 livelli — dalle foto in abiti aderenti "
            "ai contenuti premium esclusivi. Ogni livello ha un prezzo studiato strategicamente "
            "per far sì che gli abbonati spendano naturalmente sempre di più.\n\n"
            "Per i social, ti riprendi una volta con un outfit aderente (senza mostrare la pelle) "
            "e il nostro sistema IA fa il resto — cambiandoti outfit diversi, "
            "sincronizzati con la tua voce, a qualità professionale.\n\n"
            "Non devi essere una fotografa. Non ti serve attrezzatura costosa. "
            "Un telefono e una buona luce bastano per iniziare."
        ),
        "button": "Avanti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "3️⃣  IL SISTEMA DI CHAT — NON PARLI MAI CON LORO\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Questa è la domanda che fanno tutti — \"devo davvero parlare con questi tizi?\"\n\n"
            "No. Nemmeno una volta. Mai.\n\n"
            "Abbiamo creato un motore di messaggistica automatica con IA proprietario che gestisce ogni conversazione "
            "24 ore su 24, 7 giorni su 7. Usa script basati sulla psicologia "
            "per creare una connessione vera con gli abbonati e farli progredire attraverso un "
            "sistema di vendita a 6 livelli.\n\n"
            "Ognuno dei tuoi account Instagram alimenta il proprio persona IA — "
            "con la propria voce, la propria personalità e la propria strategia di conversione.\n\n"
            "Non vedi mai i messaggi. Non ti occupi mai degli scambi. "
            "I soldi arrivano, il tuo 40% va sul tuo conto. Punto."
        ),
        "button": "Avanti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "4️⃣  LA STRATEGIA MULTI-PIATTAFORMA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Ecco cosa ci distingue da tutti gli altri.\n\n"
            "Un solo account Instagram non basta. Le donne che guadagnano davvero tanto "
            "gestiscono fino a 10 account contemporaneamente — ognuno punta a "
            "una nicchia di pubblico diversa.\n\n"
            "Li costruiamo e gestiamo TUTTI per te. Ogni account ha il suo "
            "stile estetico, la sua strategia di crescita e il suo funnel che "
            "porta abbonati alla tua pagina.\n\n"
            "10 fonti di traffico invece di 1. Non è una piccola differenza — "
            "è la differenza tra 2.000 € al mese e 20.000 € al mese."
        ),
        "button": "Avanti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "5️⃣  I TUOI SOLDI E LA TUA PROTEZIONE\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Voglio essere completamente trasparente sui soldi.\n\n"
            "Usiamo Melon (getmelon.io) — una piattaforma di condivisione delle entrate di terze parti "
            "di cui si fidano più di 125 agenzie. Nel momento in cui arrivano i tuoi guadagni, Melon "
            "attiva automaticamente la divisione 60/40. Il tuo 40% va direttamente a te. "
            "Nessun trasferimento manuale. Nessuna conversazione imbarazzante.\n\n"
            "Oltre a questo, tutto è documentato in un contratto firmato prima "
            "di iniziare. I tuoi guadagni, i tuoi diritti, le nostre responsabilità — tutto per iscritto.\n\n"
            "Non ci sarà mai una domanda sui soldi perché il sistema li gestisce "
            "automaticamente e il contratto ne è la garanzia."
        ),
        "button": "Avanti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "6️⃣  LA TUA ROADMAP A 90 GIORNI\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Ecco come si presentano i primi 90 giorni:\n\n"
            "📅 Settimana 1 — Onboarding. Firmi il contratto, ti colleghi a Melon, "
            "compili il tuo profilo e inizi a girare i tuoi primi contenuti.\n\n"
            "📅 Settimane 2-4 — Gli account vanno live. I tuoi account Instagram iniziano a crescere, "
            "il sistema di chat si attiva e gli abbonati iniziano ad arrivare.\n\n"
            "📅 Mese 2 — Momentum. Entrate reali arrivano sul tuo conto. "
            "Raddoppiamo su quello che funziona.\n\n"
            "📅 Mese 3 — Scale. L'obiettivo sono 10.000 €/mese al giorno 90. "
            "L'abbiamo già fatto e lo faremo con te."
        ),
        "button": "Avanti →",
    },
    {
        "text": (
            "━━━━━━━━━━━━━━━━━━\n"
            "✅  SEI PRONTA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Questo è tutto quello che devi sapere prima della nostra chiamata.\n\n"
            "Quando parliamo, non ripeteremo niente di questo. "
            "Invece, ti configuriamo — colleghiamo i tuoi account, costruiamo il tuo profilo "
            "e pianifichiamo le tue prime due settimane di contenuti.\n\n"
            "Se hai domande prima della chiamata, scrivile qui "
            "e ti rispondo.\n\n"
            "A presto 💪"
        ),
        "button": None,
    },
]


# ═══════════════════════════════════════════════════════════════
# TRANSLATION REGISTRY
# ═══════════════════════════════════════════════════════════════

STEPS = {
    "en": STEPS_EN,
    "es": STEPS_ES,         # Neutral Spanish (tuteo) — fallback for all LatAm Spanish
    "es-AR": STEPS_ES_AR,   # Argentine/Uruguayan (voseo)
    "pt-BR": STEPS_PT_BR,   # Brazilian Portuguese
    "fr": STEPS_FR,         # French
    "de": STEPS_DE,         # German
    "it": STEPS_IT,         # Italian
}

# Acknowledgment when model sends a message
ACK_MSG = {
    "en": "Got it! the admin will get back to you shortly. 🙏",
    "es": "¡Recibido! the admin te responderá pronto. 🙏",
    "pt-BR": "Recebido! the admin vai te responder em breve. 🙏",
    "fr": "Reçu ! the admin te répondra rapidement. 🙏",
    "de": "Verstanden! the admin meldet sich in Kürze bei dir. 🙏",
    "it": "Ricevuto! the admin ti risponderà a breve. 🙏",
}

# Human-readable labels for admin notifications
LANG_LABELS = {
    "en":    "English",
    "es":    "Español",
    "es-CO": "Español (Colombia)",
    "es-AR": "Español (Argentina)",
    "es-MX": "Español (México)",
    "es-CL": "Español (Chile)",
    "es-PE": "Español (Perú)",
    "es-VE": "Español (Venezuela)",
    "es-EC": "Español (Ecuador)",
    "es-DO": "Español (Rep. Dominicana)",
    "es-UY": "Español (Uruguay)",
    "es-PY": "Español (Paraguay)",
    "es-BO": "Español (Bolivia)",
    "es-CR": "Español (Costa Rica)",
    "es-PA": "Español (Panamá)",
    "es-GT": "Español (Guatemala)",
    "es-HN": "Español (Honduras)",
    "es-SV": "Español (El Salvador)",
    "es-NI": "Español (Nicaragua)",
    "es-CU": "Español (Cuba)",
    "es-PR": "Español (Puerto Rico)",
    "es-ES": "Español (España)",
    "pt-BR": "Português (Brasil)",
    "pt-PT": "Português (Portugal)",
    "fr":    "Français",
    "de":    "Deutsch",
    "it":    "Italiano",
    "ro":    "Română",
    "ru":    "Русский",
    "uk":    "Українська",
    "pl":    "Polski",
    "ja":    "日本語",
    "ko":    "한국어",
    "zh":    "中文",
    "ar":    "العربية",
    "hi":    "हिन्दी",
    "tl":    "Filipino/Tagalog",
}


# ═══════════════════════════════════════════════════════════════
# LOCALE RESOLUTION
# ═══════════════════════════════════════════════════════════════

def resolve_steps(locale: str):
    """
    Resolve a locale code to the best matching translation.

    Resolution order:
      1. Exact match: "es-AR" → STEPS["es-AR"]
      2. Base language: "es-CO" → STEPS["es"]
      3. Fallback: "ja" → STEPS["en"]
    """
    # Exact match
    if locale in STEPS:
        return STEPS[locale]

    # Base language fallback (es-CO → es, pt-PT → pt-BR if exists)
    base = locale.split("-")[0] if "-" in locale else locale

    # Special case: pt → pt-BR (more common for our audience)
    if base == "pt" and "pt-BR" in STEPS:
        return STEPS["pt-BR"]

    if base in STEPS:
        return STEPS[base]

    # Ultimate fallback
    return STEPS["en"]


def resolve_ack(locale: str) -> str:
    """Resolve acknowledgment message for a locale."""
    if locale in ACK_MSG:
        return ACK_MSG[locale]
    base = locale.split("-")[0] if "-" in locale else locale
    if base == "pt":
        return ACK_MSG.get("pt-BR", ACK_MSG["en"])
    return ACK_MSG.get(base, ACK_MSG["en"])


def get_label(locale: str) -> str:
    """Get human-readable label for a locale."""
    return LANG_LABELS.get(locale, locale)


# ═══════════════════════════════════════════════════════════════
# COUNTRY → LOCALE MAPPING (used by the website form)
# ═══════════════════════════════════════════════════════════════
# The form sends a country-based locale code. This maps to the
# translation the bot should use.

COUNTRY_LOCALES = {
    # English
    "en":    "en",
    "en-US": "en",
    "en-GB": "en",
    "en-AU": "en",
    "en-CA": "en",

    # Spanish variants → most use neutral, AR/UY get voseo
    "es-CO": "es",       # Colombia → neutral
    "es-MX": "es",       # Mexico → neutral
    "es-CL": "es",       # Chile → neutral
    "es-PE": "es",       # Peru → neutral
    "es-VE": "es",       # Venezuela → neutral
    "es-EC": "es",       # Ecuador → neutral
    "es-DO": "es",       # Dominican Republic → neutral
    "es-PY": "es",       # Paraguay → neutral
    "es-BO": "es",       # Bolivia → neutral
    "es-CR": "es",       # Costa Rica → neutral
    "es-PA": "es",       # Panama → neutral
    "es-GT": "es",       # Guatemala → neutral
    "es-HN": "es",       # Honduras → neutral
    "es-SV": "es",       # El Salvador → neutral
    "es-NI": "es",       # Nicaragua → neutral
    "es-CU": "es",       # Cuba → neutral
    "es-PR": "es",       # Puerto Rico → neutral
    "es-ES": "es",       # Spain → neutral
    "es-AR": "es-AR",    # Argentina → voseo
    "es-UY": "es-AR",    # Uruguay → voseo (same as Argentina)

    # Portuguese
    "pt-BR": "pt-BR",    # Brazil
    "pt-PT": "pt-BR",    # Portugal → falls back to Brazilian for now

    # European languages — now fully translated
    "fr":    "fr",
    "de":    "de",
    "it":    "it",
    "ro":    "en",
    "ru":    "en",
    "uk":    "en",
    "pl":    "en",
    "ja":    "en",
    "ko":    "en",
    "zh":    "en",
    "ar":    "en",
    "hi":    "en",
    "tl":    "en",
}
