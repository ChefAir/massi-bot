"""
Massi-Bot — Model Profile Onboarding Flow
==========================================
Triggered from the Telegram onboarding bot after pre-education is complete.
Collects all ModelProfile fields via structured Q&A with inline keyboards.
Saves to Supabase models table (profile_json column).

Flow:
  Step 0:  Welcome + consent
  Step 1:  Stage name
  Step 2:  Age
  Step 3:  Ethnicity (keyboard)
  Step 4:  Hair color (keyboard)
  Step 5:  Hair length (keyboard)
  Step 6:  Body type (keyboard)
  Step 7:  Height (free text)
  Step 8:  Notable features (free text)
  Step 9:  Face in tease content? (keyboard)
  Step 10: Face in explicit content? (keyboard)
  Step 11: Will do (multi-select keyboard)
  Step 12: Won't do (free text)
  Step 13: Shooting locations (multi-select keyboard)
  Step 14: Wardrobe (free text)
  Step 15: Personality description (free text)
  Step 16: Speaking style (free text)
  Step 17: Timezone / location (free text)
  Step 18: Done → save to Supabase
"""

import json
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Profile step definitions
PROFILE_STEPS = [
    {
        "key": "_welcome",
        "question": (
            "✨ *One last thing before your call!*\n\n"
            "I need to collect some info about you so we can personalize everything — "
            "your content descriptions, your messaging style, and how we represent you.\n\n"
            "This stays 100% private. Takes about 5 minutes.\n\n"
            "Let's go! 👇"
        ),
        "type": "confirm",
        "button_text": "Let's do it →",
    },
    {
        "key": "stage_name",
        "question": "What's your *stage name*? (The name you'll use on Fanvue/OnlyFans)",
        "type": "text",
        "placeholder": "e.g. Mia Rose",
    },
    {
        "key": "age",
        "question": "How old are you?",
        "type": "keyboard",
        "options": [["18", "19", "20", "21"], ["22", "23", "24", "25"], ["26", "27", "28", "29"], ["30+"]],
    },
    {
        "key": "ethnicity",
        "question": "How would you describe your ethnicity?",
        "type": "keyboard",
        "options": [
            ["White / European", "Latina"],
            ["Black / African", "Asian"],
            ["Middle Eastern", "South Asian"],
            ["Mixed", "Other"],
        ],
    },
    {
        "key": "hair_color",
        "question": "What's your natural hair color?",
        "type": "keyboard",
        "options": [
            ["Brunette 🟤", "Blonde 🟡"],
            ["Black ⚫", "Red 🔴"],
            ["Auburn", "Gray / Silver"],
            ["Dyed / Other"],
        ],
    },
    {
        "key": "hair_length",
        "question": "How long is your hair?",
        "type": "keyboard",
        "options": [["Short (above shoulders)", "Medium (shoulder length)"], ["Long (chest+)", "Very long (waist+)"]],
    },
    {
        "key": "body_type",
        "question": "How would you describe your body type?",
        "type": "keyboard",
        "options": [
            ["Slim / Petite", "Athletic / Toned"],
            ["Curvy", "Thick / BBW"],
            ["Average"],
        ],
    },
    {
        "key": "height",
        "question": "What's your height? (e.g. 5'4\" or 163 cm)",
        "type": "text",
        "placeholder": "e.g. 5'6\"",
    },
    {
        "key": "notable_features",
        "question": (
            "Any notable features? Tattoos, piercings, freckles, etc.\n\n"
            "_(Type 'none' if nothing notable)_"
        ),
        "type": "text",
        "placeholder": "e.g. small tattoo on left hip, nose ring, freckles",
    },
    {
        "key": "face_in_tease",
        "question": "Do you want your *face to be visible* in teasing content (clothed, non-explicit)?",
        "type": "keyboard",
        "options": [["✅ Yes, face visible", "❌ No, no face"]],
    },
    {
        "key": "face_in_explicit",
        "question": "Do you want your *face to be visible* in explicit content (Tiers 3-6)?",
        "type": "keyboard",
        "options": [["✅ Yes, face visible", "🚫 No face in explicit"]],
    },
    {
        "key": "will_do",
        "question": (
            "What content are you comfortable creating? ✅\n\n"
            "_(Type all that apply, separated by commas)_\n\n"
            "Options: solo, toys, lingerie, implied nudity, topless, full nude, self-play, riding, dirty talk audio"
        ),
        "type": "text",
        "placeholder": "e.g. solo, toys, lingerie, topless, full nude",
    },
    {
        "key": "wont_do",
        "question": (
            "What are your *hard limits*? 🚫\n\n"
            "_(Type all that apply, or 'none')_\n\n"
            "Common: no face in explicit, no boy-girl, no extreme content, no certain body shots"
        ),
        "type": "text",
        "placeholder": "e.g. no face in explicit, no boy-girl",
    },
    {
        "key": "shooting_locations",
        "question": (
            "Where can you shoot content? 📍\n\n"
            "_(Select all that apply)_"
        ),
        "type": "multi_keyboard",
        "options": [
            ["🛏️ Bedroom", "🚿 Bathroom"],
            ["🛋️ Living Room", "🍳 Kitchen"],
            ["🪞 Mirror area", "🌊 Outdoors / Pool"],
            ["Done ✅"],
        ],
        "done_text": "Done ✅",
    },
    {
        "key": "wardrobe",
        "question": (
            "What outfits / wardrobe do you have available for shoots?\n\n"
            "_(Be specific — this helps us write accurate content descriptions)_"
        ),
        "type": "text",
        "placeholder": "e.g. black lingerie set, white oversized tee, bikini, gym clothes, little black dress",
    },
    {
        "key": "natural_personality",
        "question": (
            "How would you describe your *personality* in 3-5 words?\n\n"
            "_(This shapes how the chatbot communicates as you)_"
        ),
        "type": "text",
        "placeholder": "e.g. bubbly, flirty, sweet, a little sarcastic",
    },
    {
        "key": "natural_speaking_style",
        "question": (
            "How do you naturally text / talk?\n\n"
            "_(Slang, tone, emoji usage — be yourself)_"
        ),
        "type": "text",
        "placeholder": "e.g. lots of lowercase, uses lol and omg, sends emojis constantly, Gen Z casual",
    },
    {
        "key": "stated_location",
        "question": (
            "Where are you *located* (or where do you want to say you're from)?\n\n"
            "_(City/country is fine — this is used in conversation, not for legal purposes)_"
        ),
        "type": "text",
        "placeholder": "e.g. Miami, Florida or Medellín, Colombia",
    },
    {
        "key": "phone_model",
        "question": (
            "What phone do you use to take photos and videos? 📱\n\n"
            "_(This helps us give you the exact camera settings for the best quality)_"
        ),
        "type": "keyboard",
        "options": [
            ["iPhone 17 Pro / Pro Max", "iPhone 17 / Air"],
            ["iPhone 17e", "iPhone 16 Pro / Pro Max"],
            ["iPhone 16 / 16 Plus", "iPhone 16e"],
            ["iPhone 15 Pro / Pro Max", "iPhone 15 / 15 Plus"],
            ["iPhone 14 or older", "Samsung Galaxy S25 series"],
            ["Samsung Galaxy S24 / S23", "Other Android"],
            ["⌨️ Other / Type mine →"],
        ],
    },
]

TOTAL_STEPS = len(PROFILE_STEPS)

# ─────────────────────────────────────────────────────────────────────────────
# PROFILE I18N — Static translations for questions, button labels, keyboard
# options, and profile summary labels. Avoids LLM dependency for the Q&A flow.
# callback_data always stays in English — only display labels are translated.
# ─────────────────────────────────────────────────────────────────────────────

_PROFILE_I18N: dict = {
    "es": {
        "questions": {
            "_welcome": (
                "✨ *¡Una última cosa antes de tu llamada!*\n\n"
                "Necesito recopilar información sobre ti para personalizarlo todo — "
                "tus descripciones de contenido, tu estilo de mensajes y cómo te representamos.\n\n"
                "Esto es 100% privado. Toma unos 5 minutos.\n\n"
                "¡Vamos! 👇"
            ),
            "stage_name": "¿Cuál es tu *nombre artístico*? (El nombre que usarás en Fanvue/OnlyFans)",
            "age": "¿Cuántos años tienes?",
            "ethnicity": "¿Cómo describirías tu etnicidad?",
            "hair_color": "¿Cuál es tu color de cabello natural?",
            "hair_length": "¿Qué tan largo tienes el cabello?",
            "body_type": "¿Cómo describirías tu tipo de cuerpo?",
            "height": "¿Cuánto mides? (ej. 5'4\" o 163 cm)",
            "notable_features": (
                "¿Tienes algún rasgo notable? Tatuajes, piercings, pecas, etc.\n\n"
                "_(Escribe 'ninguno' si no hay nada notable)_"
            ),
            "face_in_tease": "¿Quieres que tu *cara sea visible* en contenido sugerente (con ropa, no explícito)?",
            "face_in_explicit": "¿Quieres que tu *cara sea visible* en contenido explícito (Niveles 3-6)?",
            "will_do": (
                "¿Qué tipo de contenido te sientes cómoda creando? ✅\n\n"
                "_(Escribe todo lo que aplique, separado por comas)_\n\n"
                "Opciones: solo, juguetes, lencería, desnudo implícito, topless, desnudo completo, autosatisfacción, riding, audio picante"
            ),
            "wont_do": (
                "¿Cuáles son tus *límites absolutos*? 🚫\n\n"
                "_(Escribe todo lo que aplique, o 'ninguno')_\n\n"
                "Comunes: sin cara en explícito, sin pareja chico-chica, sin contenido extremo, sin ciertos planos del cuerpo"
            ),
            "shooting_locations": "¿Dónde puedes filmar contenido? 📍\n\n_(Selecciona todo lo que aplique)_",
            "wardrobe": (
                "¿Qué ropa / guardarropa tienes disponible para las sesiones?\n\n"
                "_(Sé específica — esto nos ayuda a escribir descripciones precisas del contenido)_"
            ),
            "natural_personality": (
                "¿Cómo describirías tu *personalidad* en 3-5 palabras?\n\n"
                "_(Esto define cómo el chatbot se comunica como tú)_"
            ),
            "natural_speaking_style": (
                "¿Cómo escribes / hablas naturalmente?\n\n"
                "_(Jerga, tono, uso de emojis — sé tú misma)_"
            ),
            "stated_location": (
                "¿Dónde estás *ubicada* (o de dónde quieres decir que eres)?\n\n"
                "_(Ciudad/país está bien — se usa en conversación, no con fines legales)_"
            ),
            "phone_model": (
                "¿Qué teléfono usas para tomar fotos y videos? 📱\n\n"
                "_(Esto nos ayuda a darte la configuración exacta de cámara para la mejor calidad)_"
            ),
        },
        "buttons": {"_welcome": "¡Vamos! →"},
        "options": {
            "ethnicity": [
                ["Blanca / Europea", "Latina"],
                ["Negra / Africana", "Asiática"],
                ["Árabe / Oriente Medio", "Sur Asiática"],
                ["Mixta", "Otra"],
            ],
            "hair_color": [
                ["Morena 🟤", "Rubia 🟡"],
                ["Negra ⚫", "Roja 🔴"],
                ["Castaña rojiza", "Gris / Plata"],
                ["Teñida / Otra"],
            ],
            "hair_length": [
                ["Corto (sobre los hombros)", "Medio (a la altura de los hombros)"],
                ["Largo (hasta el pecho+)", "Muy largo (hasta la cintura+)"],
            ],
            "body_type": [
                ["Delgada / Petite", "Atlética / Tonificada"],
                ["Curvilínea", "Rellenita / BBW"],
                ["Promedio"],
            ],
            "face_in_tease": [["✅ Sí, cara visible", "❌ No, sin cara"]],
            "face_in_explicit": [["✅ Sí, cara visible", "🚫 Sin cara en explícito"]],
            "shooting_locations": [
                ["🛏️ Habitación", "🚿 Baño"],
                ["🛋️ Sala de estar", "🍳 Cocina"],
                ["🪞 Zona de espejo", "🌊 Al aire libre / Piscina"],
                ["Listo ✅"],
            ],
            "phone_model": [
                ["iPhone 17 Pro / Pro Max", "iPhone 17 / Air"],
                ["iPhone 17e", "iPhone 16 Pro / Pro Max"],
                ["iPhone 16 / 16 Plus", "iPhone 16e"],
                ["iPhone 15 Pro / Pro Max", "iPhone 15 / 15 Plus"],
                ["iPhone 14 o anterior", "Samsung Galaxy S25 series"],
                ["Samsung Galaxy S24 / S23", "Otro Android"],
                ["⌨️ Otro / Escribir el mío →"],
            ],
        },
        "summary": {
            "title": "📋 *RESUMEN DE TU PERFIL*",
            "stage_name": "🎭 Nombre artístico",
            "age": "🎂 Edad",
            "from": "🌎 De",
            "ethnicity": "👤 Etnicidad",
            "hair": "💇 Cabello",
            "body": "💪 Cuerpo",
            "features": "✨ Rasgos",
            "face_tease": "📸 Cara en sugerente",
            "face_explicit": "🔞 Cara en explícito",
            "will_do": "✅ Hará",
            "wont_do": "🚫 No hará",
            "locations": "📍 Ubicaciones",
            "wardrobe": "👗 Guardarropa",
            "personality": "💬 Personalidad",
            "speaking": "🗣️ Estilo de comunicación",
            "complete": "✅ ¡Perfil completo!",
        },
    },
    "pt-BR": {
        "questions": {
            "_welcome": (
                "✨ *Uma última coisa antes da sua chamada!*\n\n"
                "Preciso coletar algumas informações sobre você para personalizar tudo — "
                "as descrições do seu conteúdo, seu estilo de mensagens e como te representamos.\n\n"
                "Isso fica 100% privado. Leva cerca de 5 minutos.\n\n"
                "Vamos lá! 👇"
            ),
            "stage_name": "Qual é o seu *nome artístico*? (O nome que você vai usar no Fanvue/OnlyFans)",
            "age": "Quantos anos você tem?",
            "ethnicity": "Como você descreveria sua etnia?",
            "hair_color": "Qual é a sua cor de cabelo natural?",
            "hair_length": "Qual é o comprimento do seu cabelo?",
            "body_type": "Como você descreveria seu tipo de corpo?",
            "height": "Qual é a sua altura? (ex. 5'4\" ou 163 cm)",
            "notable_features": (
                "Você tem algum traço marcante? Tatuagens, piercings, sardas, etc.\n\n"
                "_(Digite 'nenhum' se não houver nada de especial)_"
            ),
            "face_in_tease": "Você quer que seu *rosto apareça* em conteúdo sugestivo (com roupa, não explícito)?",
            "face_in_explicit": "Você quer que seu *rosto apareça* em conteúdo explícito (Níveis 3-6)?",
            "will_do": (
                "Que tipo de conteúdo você se sente confortável criando? ✅\n\n"
                "_(Digite tudo que se aplica, separado por vírgulas)_\n\n"
                "Opções: solo, brinquedos, lingerie, nudez implícita, topless, nu completo, autoerotismo, riding, áudio ousado"
            ),
            "wont_do": (
                "Quais são seus *limites absolutos*? 🚫\n\n"
                "_(Digite tudo que se aplica, ou 'nenhum')_\n\n"
                "Comuns: sem rosto no explícito, sem casal hetero, sem conteúdo extremo, sem certos ângulos do corpo"
            ),
            "shooting_locations": "Onde você pode filmar conteúdo? 📍\n\n_(Selecione tudo que se aplica)_",
            "wardrobe": (
                "Quais roupas / figurinos você tem disponíveis para as gravações?\n\n"
                "_(Seja específica — isso nos ajuda a escrever descrições precisas do conteúdo)_"
            ),
            "natural_personality": (
                "Como você descreveria sua *personalidade* em 3-5 palavras?\n\n"
                "_(Isso define como o chatbot se comunica como você)_"
            ),
            "natural_speaking_style": (
                "Como você escreve / fala naturalmente?\n\n"
                "_(Gírias, tom, uso de emojis — seja você mesma)_"
            ),
            "stated_location": (
                "Onde você está *localizada* (ou de onde quer dizer que é)?\n\n"
                "_(Cidade/país está ótimo — usado em conversa, não para fins legais)_"
            ),
            "phone_model": (
                "Qual celular você usa para tirar fotos e vídeos? 📱\n\n"
                "_(Isso nos ajuda a te dar as configurações exatas de câmera para a melhor qualidade)_"
            ),
        },
        "buttons": {"_welcome": "Vamos lá! →"},
        "options": {
            "ethnicity": [
                ["Branca / Europeia", "Latina"],
                ["Negra / Africana", "Asiática"],
                ["Árabe / Oriente Médio", "Sul Asiática"],
                ["Mestiça", "Outra"],
            ],
            "hair_color": [
                ["Morena 🟤", "Loira 🟡"],
                ["Preta ⚫", "Ruiva 🔴"],
                ["Castanho avermelhado", "Grisalha / Prata"],
                ["Colorida / Outra"],
            ],
            "hair_length": [
                ["Curto (acima dos ombros)", "Médio (na altura dos ombros)"],
                ["Longo (até o peito+)", "Muito longo (até a cintura+)"],
            ],
            "body_type": [
                ["Magra / Petite", "Atlética / Definida"],
                ["Curvilínea", "Gordinha / BBW"],
                ["Mediana"],
            ],
            "face_in_tease": [["✅ Sim, rosto visível", "❌ Não, sem rosto"]],
            "face_in_explicit": [["✅ Sim, rosto visível", "🚫 Sem rosto no explícito"]],
            "shooting_locations": [
                ["🛏️ Quarto", "🚿 Banheiro"],
                ["🛋️ Sala de estar", "🍳 Cozinha"],
                ["🪞 Área do espelho", "🌊 Ao ar livre / Piscina"],
                ["Pronto ✅"],
            ],
            "phone_model": [
                ["iPhone 17 Pro / Pro Max", "iPhone 17 / Air"],
                ["iPhone 17e", "iPhone 16 Pro / Pro Max"],
                ["iPhone 16 / 16 Plus", "iPhone 16e"],
                ["iPhone 15 Pro / Pro Max", "iPhone 15 / 15 Plus"],
                ["iPhone 14 ou anterior", "Samsung Galaxy S25 series"],
                ["Samsung Galaxy S24 / S23", "Outro Android"],
                ["⌨️ Outro / Digitar o meu →"],
            ],
        },
        "summary": {
            "title": "📋 *RESUMO DO SEU PERFIL*",
            "stage_name": "🎭 Nome artístico",
            "age": "🎂 Idade",
            "from": "🌎 De",
            "ethnicity": "👤 Etnia",
            "hair": "💇 Cabelo",
            "body": "💪 Corpo",
            "features": "✨ Traços",
            "face_tease": "📸 Rosto no sugestivo",
            "face_explicit": "🔞 Rosto no explícito",
            "will_do": "✅ Fará",
            "wont_do": "🚫 Não fará",
            "locations": "📍 Locações",
            "wardrobe": "👗 Figurinos",
            "personality": "💬 Personalidade",
            "speaking": "🗣️ Estilo de comunicação",
            "complete": "✅ Perfil completo!",
        },
    },
    "fr": {
        "questions": {
            "_welcome": (
                "✨ *Une dernière chose avant ton appel !*\n\n"
                "J'ai besoin de collecter quelques infos sur toi pour tout personnaliser — "
                "tes descriptions de contenu, ton style de messages et comment on te représente.\n\n"
                "C'est 100% privé. Ça prend environ 5 minutes.\n\n"
                "C'est parti ! 👇"
            ),
            "stage_name": "Quel est ton *nom de scène* ? (Le nom que tu utiliseras sur Fanvue/OnlyFans)",
            "age": "Quel âge as-tu ?",
            "ethnicity": "Comment décrirais-tu ton origine ethnique ?",
            "hair_color": "Quelle est ta couleur de cheveux naturelle ?",
            "hair_length": "Quelle est la longueur de tes cheveux ?",
            "body_type": "Comment décrirais-tu ton type de corps ?",
            "height": "Quelle est ta taille ? (ex. 1m63 ou 5'4\")",
            "notable_features": (
                "Tu as des particularités notables ? Tatouages, piercings, taches de rousseur, etc.\n\n"
                "_(Tape 'aucun' si rien de notable)_"
            ),
            "face_in_tease": "Tu veux que ton *visage soit visible* dans le contenu suggestif (habillé, non explicite) ?",
            "face_in_explicit": "Tu veux que ton *visage soit visible* dans le contenu explicite (Niveaux 3-6) ?",
            "will_do": (
                "Quel type de contenu es-tu à l'aise pour créer ? ✅\n\n"
                "_(Tape tout ce qui s'applique, séparé par des virgules)_\n\n"
                "Options : solo, jouets, lingerie, nudité implicite, topless, nu intégral, solo érotique, riding, audio hot"
            ),
            "wont_do": (
                "Quelles sont tes *limites absolues* ? 🚫\n\n"
                "_(Tape tout ce qui s'applique, ou 'aucun')_\n\n"
                "Courants : pas de visage en explicite, pas de couple mixte, pas de contenu extrême, pas certains plans du corps"
            ),
            "shooting_locations": "Où peux-tu tourner du contenu ? 📍\n\n_(Sélectionne tout ce qui s'applique)_",
            "wardrobe": (
                "Quelles tenues / garde-robe as-tu disponibles pour les tournages ?\n\n"
                "_(Sois précise — ça nous aide à écrire des descriptions précises du contenu)_"
            ),
            "natural_personality": (
                "Comment décrirais-tu ta *personnalité* en 3-5 mots ?\n\n"
                "_(Ça définit comment le chatbot communique en tant que toi)_"
            ),
            "natural_speaking_style": (
                "Comment tu textes / parles naturellement ?\n\n"
                "_(Argot, ton, utilisation des emojis — sois toi-même)_"
            ),
            "stated_location": (
                "Où es-tu *basée* (ou d'où veux-tu dire que tu viens) ?\n\n"
                "_(Ville/pays c'est bien — utilisé dans les conversations, pas à des fins légales)_"
            ),
            "phone_model": (
                "Quel téléphone utilises-tu pour prendre des photos et vidéos ? 📱\n\n"
                "_(Ça nous aide à te donner les réglages de caméra exacts pour la meilleure qualité)_"
            ),
        },
        "buttons": {"_welcome": "C'est parti ! →"},
        "options": {
            "ethnicity": [
                ["Blanche / Européenne", "Latina"],
                ["Noire / Africaine", "Asiatique"],
                ["Moyen-Orient / Arabe", "Sud-Asiatique"],
                ["Métissée", "Autre"],
            ],
            "hair_color": [
                ["Brune 🟤", "Blonde 🟡"],
                ["Noire ⚫", "Rousse 🔴"],
                ["Châtain roux", "Gris / Argenté"],
                ["Colorés / Autre"],
            ],
            "hair_length": [
                ["Courts (au-dessus des épaules)", "Moyens (à la hauteur des épaules)"],
                ["Longs (jusqu'à la poitrine+)", "Très longs (jusqu'à la taille+)"],
            ],
            "body_type": [
                ["Mince / Petite", "Athlétique / Tonique"],
                ["Pulpeuse", "Ronde / BBW"],
                ["Moyenne"],
            ],
            "face_in_tease": [["✅ Oui, visage visible", "❌ Non, sans visage"]],
            "face_in_explicit": [["✅ Oui, visage visible", "🚫 Sans visage en explicite"]],
            "shooting_locations": [
                ["🛏️ Chambre", "🚿 Salle de bain"],
                ["🛋️ Salon", "🍳 Cuisine"],
                ["🪞 Zone miroir", "🌊 Extérieur / Piscine"],
                ["Terminé ✅"],
            ],
            "phone_model": [
                ["iPhone 17 Pro / Pro Max", "iPhone 17 / Air"],
                ["iPhone 17e", "iPhone 16 Pro / Pro Max"],
                ["iPhone 16 / 16 Plus", "iPhone 16e"],
                ["iPhone 15 Pro / Pro Max", "iPhone 15 / 15 Plus"],
                ["iPhone 14 ou ancien", "Samsung Galaxy S25 series"],
                ["Samsung Galaxy S24 / S23", "Autre Android"],
                ["⌨️ Autre / Taper le mien →"],
            ],
        },
        "summary": {
            "title": "📋 *RÉSUMÉ DE TON PROFIL*",
            "stage_name": "🎭 Nom de scène",
            "age": "🎂 Âge",
            "from": "🌎 De",
            "ethnicity": "👤 Origine",
            "hair": "💇 Cheveux",
            "body": "💪 Corps",
            "features": "✨ Particularités",
            "face_tease": "📸 Visage en suggestif",
            "face_explicit": "🔞 Visage en explicite",
            "will_do": "✅ Fera",
            "wont_do": "🚫 Ne fera pas",
            "locations": "📍 Lieux",
            "wardrobe": "👗 Garde-robe",
            "personality": "💬 Personnalité",
            "speaking": "🗣️ Style de communication",
            "complete": "✅ Profil complet !",
        },
    },
    "de": {
        "questions": {
            "_welcome": (
                "✨ *Noch eine letzte Sache vor deinem Gespräch!*\n\n"
                "Ich muss einige Infos über dich sammeln, um alles zu personalisieren — "
                "deine Inhaltsbeschreibungen, deinen Nachrichtenstil und wie wir dich repräsentieren.\n\n"
                "Das bleibt 100% privat. Dauert etwa 5 Minuten.\n\n"
                "Los geht's! 👇"
            ),
            "stage_name": "Was ist dein *Künstlername*? (Der Name, den du auf Fanvue/OnlyFans verwenden wirst)",
            "age": "Wie alt bist du?",
            "ethnicity": "Wie würdest du deine Herkunft beschreiben?",
            "hair_color": "Was ist deine natürliche Haarfarbe?",
            "hair_length": "Wie lang ist dein Haar?",
            "body_type": "Wie würdest du deinen Körpertyp beschreiben?",
            "height": "Wie groß bist du? (z.B. 1,63 m oder 5'4\")",
            "notable_features": (
                "Hast du besondere Merkmale? Tattoos, Piercings, Sommersprossen, etc.\n\n"
                "_(Schreibe 'keine' wenn nichts Besonderes)_"
            ),
            "face_in_tease": "Soll dein *Gesicht sichtbar* sein in verführerischen Inhalten (bekleidet, nicht explizit)?",
            "face_in_explicit": "Soll dein *Gesicht sichtbar* sein in expliziten Inhalten (Stufen 3-6)?",
            "will_do": (
                "Bei welchen Inhalten bist du komfortabel? ✅\n\n"
                "_(Schreibe alles was zutrifft, durch Komma getrennt)_\n\n"
                "Optionen: Solo, Toys, Dessous, angedeutete Nacktheit, Oben-ohne, komplett nackt, Selbstbefriedigung, Reiten, Erotik-Audio"
            ),
            "wont_do": (
                "Was sind deine *absoluten Grenzen*? 🚫\n\n"
                "_(Schreibe alles was zutrifft, oder 'keine')_\n\n"
                "Häufig: kein Gesicht in explizit, kein Pärchen, kein extremer Inhalt, keine bestimmten Körperaufnahmen"
            ),
            "shooting_locations": "Wo kannst du Inhalte aufnehmen? 📍\n\n_(Wähle alles was zutrifft)_",
            "wardrobe": (
                "Welche Outfits / Garderobe hast du für Aufnahmen?\n\n"
                "_(Sei konkret — das hilft uns genaue Inhaltsbeschreibungen zu schreiben)_"
            ),
            "natural_personality": (
                "Wie würdest du deine *Persönlichkeit* in 3-5 Worten beschreiben?\n\n"
                "_(Das prägt wie der Chatbot als du kommuniziert)_"
            ),
            "natural_speaking_style": (
                "Wie schreibst / redest du natürlich?\n\n"
                "_(Slang, Ton, Emoji-Nutzung — sei du selbst)_"
            ),
            "stated_location": (
                "Wo bist du *ansässig* (oder wo möchtest du sagen, dass du herkommst)?\n\n"
                "_(Stadt/Land ist prima — wird in Gesprächen verwendet, nicht für rechtliche Zwecke)_"
            ),
            "phone_model": (
                "Welches Telefon benutzt du für Fotos und Videos? 📱\n\n"
                "_(Das hilft uns dir die genauen Kameraeinstellungen für beste Qualität zu geben)_"
            ),
        },
        "buttons": {"_welcome": "Los geht's! →"},
        "options": {
            "ethnicity": [
                ["Weiß / Europäisch", "Latina"],
                ["Schwarz / Afrikanisch", "Asiatisch"],
                ["Nahöstlich / Arabisch", "Südasiatisch"],
                ["Gemischt", "Andere"],
            ],
            "hair_color": [
                ["Brünett 🟤", "Blond 🟡"],
                ["Schwarz ⚫", "Rot 🔴"],
                ["Kastanienbraun", "Grau / Silber"],
                ["Gefärbt / Andere"],
            ],
            "hair_length": [
                ["Kurz (über Schultern)", "Mittel (Schulterlänge)"],
                ["Lang (bis zur Brust+)", "Sehr lang (bis zur Taille+)"],
            ],
            "body_type": [
                ["Schlank / Zierlich", "Athletisch / Trainiert"],
                ["Kurvig", "Vollschlank / BBW"],
                ["Durchschnittlich"],
            ],
            "face_in_tease": [["✅ Ja, Gesicht sichtbar", "❌ Nein, kein Gesicht"]],
            "face_in_explicit": [["✅ Ja, Gesicht sichtbar", "🚫 Kein Gesicht in explizit"]],
            "shooting_locations": [
                ["🛏️ Schlafzimmer", "🚿 Badezimmer"],
                ["🛋️ Wohnzimmer", "🍳 Küche"],
                ["🪞 Spiegelbereich", "🌊 Draußen / Pool"],
                ["Fertig ✅"],
            ],
            "phone_model": [
                ["iPhone 17 Pro / Pro Max", "iPhone 17 / Air"],
                ["iPhone 17e", "iPhone 16 Pro / Pro Max"],
                ["iPhone 16 / 16 Plus", "iPhone 16e"],
                ["iPhone 15 Pro / Pro Max", "iPhone 15 / 15 Plus"],
                ["iPhone 14 oder älter", "Samsung Galaxy S25 series"],
                ["Samsung Galaxy S24 / S23", "Anderes Android"],
                ["⌨️ Anderes / Selbst eingeben →"],
            ],
        },
        "summary": {
            "title": "📋 *DEINE PROFILZUSAMMENFASSUNG*",
            "stage_name": "🎭 Künstlername",
            "age": "🎂 Alter",
            "from": "🌎 Aus",
            "ethnicity": "👤 Herkunft",
            "hair": "💇 Haare",
            "body": "💪 Körper",
            "features": "✨ Besonderheiten",
            "face_tease": "📸 Gesicht in verführerisch",
            "face_explicit": "🔞 Gesicht in explizit",
            "will_do": "✅ Macht",
            "wont_do": "🚫 Macht nicht",
            "locations": "📍 Drehorte",
            "wardrobe": "👗 Garderobe",
            "personality": "💬 Persönlichkeit",
            "speaking": "🗣️ Kommunikationsstil",
            "complete": "✅ Profil vollständig!",
        },
    },
    "it": {
        "questions": {
            "_welcome": (
                "✨ *Un'ultima cosa prima della tua chiamata!*\n\n"
                "Ho bisogno di raccogliere alcune informazioni su di te per personalizzare tutto — "
                "le descrizioni dei tuoi contenuti, il tuo stile di messaggi e come ti rappresentiamo.\n\n"
                "Rimane al 100% privato. Richiede circa 5 minuti.\n\n"
                "Andiamo! 👇"
            ),
            "stage_name": "Qual è il tuo *nome d'arte*? (Il nome che userai su Fanvue/OnlyFans)",
            "age": "Quanti anni hai?",
            "ethnicity": "Come descriveresti la tua etnia?",
            "hair_color": "Qual è il tuo colore di capelli naturale?",
            "hair_length": "Quanto sono lunghi i tuoi capelli?",
            "body_type": "Come descriveresti il tuo tipo di corpo?",
            "height": "Quanto sei alta? (es. 1,63 m o 5'4\")",
            "notable_features": (
                "Hai caratteristiche particolari? Tatuaggi, piercing, lentiggini, ecc.\n\n"
                "_(Scrivi 'nessuno' se non c'è nulla di particolare)_"
            ),
            "face_in_tease": "Vuoi che il tuo *viso sia visibile* nei contenuti sensuali (con vestiti, non espliciti)?",
            "face_in_explicit": "Vuoi che il tuo *viso sia visibile* nei contenuti espliciti (Livelli 3-6)?",
            "will_do": (
                "Con quale tipo di contenuto sei a tuo agio? ✅\n\n"
                "_(Scrivi tutto ciò che si applica, separato da virgole)_\n\n"
                "Opzioni: solo, giocattoli, lingerie, nudità implicita, topless, nudo completo, autoerotismo, riding, audio erotico"
            ),
            "wont_do": (
                "Quali sono i tuoi *limiti assoluti*? 🚫\n\n"
                "_(Scrivi tutto ciò che si applica, o 'nessuno')_\n\n"
                "Comuni: niente viso in esplicito, niente coppia, niente contenuto estremo, niente certi angoli del corpo"
            ),
            "shooting_locations": "Dove puoi girare contenuto? 📍\n\n_(Seleziona tutto ciò che si applica)_",
            "wardrobe": (
                "Quali outfit / guardaroba hai disponibili per le riprese?\n\n"
                "_(Sii specifica — questo ci aiuta a scrivere descrizioni accurate del contenuto)_"
            ),
            "natural_personality": (
                "Come descriveresti la tua *personalità* in 3-5 parole?\n\n"
                "_(Questo definisce come il chatbot comunica come te)_"
            ),
            "natural_speaking_style": (
                "Come scrivi / parli naturalmente?\n\n"
                "_(Slang, tono, uso degli emoji — sii te stessa)_"
            ),
            "stated_location": (
                "Dove sei *basata* (o da dove vuoi dire di venire)?\n\n"
                "_(Città/paese va bene — usato nelle conversazioni, non a fini legali)_"
            ),
            "phone_model": (
                "Quale telefono usi per fare foto e video? 📱\n\n"
                "_(Questo ci aiuta a darti le impostazioni esatte della fotocamera per la migliore qualità)_"
            ),
        },
        "buttons": {"_welcome": "Andiamo! →"},
        "options": {
            "ethnicity": [
                ["Bianca / Europea", "Latina"],
                ["Nera / Africana", "Asiatica"],
                ["Mediorientale / Araba", "Sud Asiatica"],
                ["Mista", "Altra"],
            ],
            "hair_color": [
                ["Castana 🟤", "Bionda 🟡"],
                ["Nera ⚫", "Rossa 🔴"],
                ["Castano ramato", "Grigio / Argento"],
                ["Tinta / Altra"],
            ],
            "hair_length": [
                ["Corti (sopra le spalle)", "Medi (altezza spalle)"],
                ["Lunghi (fino al petto+)", "Molto lunghi (fino alla vita+)"],
            ],
            "body_type": [
                ["Magra / Petite", "Atletica / Tonica"],
                ["Formosa", "Rotonda / BBW"],
                ["Media"],
            ],
            "face_in_tease": [["✅ Sì, viso visibile", "❌ No, senza viso"]],
            "face_in_explicit": [["✅ Sì, viso visibile", "🚫 Senza viso in esplicito"]],
            "shooting_locations": [
                ["🛏️ Camera da letto", "🚿 Bagno"],
                ["🛋️ Soggiorno", "🍳 Cucina"],
                ["🪞 Zona specchio", "🌊 Esterno / Piscina"],
                ["Fatto ✅"],
            ],
            "phone_model": [
                ["iPhone 17 Pro / Pro Max", "iPhone 17 / Air"],
                ["iPhone 17e", "iPhone 16 Pro / Pro Max"],
                ["iPhone 16 / 16 Plus", "iPhone 16e"],
                ["iPhone 15 Pro / Pro Max", "iPhone 15 / 15 Plus"],
                ["iPhone 14 o precedente", "Samsung Galaxy S25 series"],
                ["Samsung Galaxy S24 / S23", "Altro Android"],
                ["⌨️ Altro / Inserire il mio →"],
            ],
        },
        "summary": {
            "title": "📋 *RIEPILOGO DEL TUO PROFILO*",
            "stage_name": "🎭 Nome d'arte",
            "age": "🎂 Età",
            "from": "🌎 Da",
            "ethnicity": "👤 Etnia",
            "hair": "💇 Capelli",
            "body": "💪 Corpo",
            "features": "✨ Caratteristiche",
            "face_tease": "📸 Viso in sensuale",
            "face_explicit": "🔞 Viso in esplicito",
            "will_do": "✅ Farà",
            "wont_do": "🚫 Non farà",
            "locations": "📍 Location",
            "wardrobe": "👗 Guardaroba",
            "personality": "💬 Personalità",
            "speaking": "🗣️ Stile comunicativo",
            "complete": "✅ Profilo completato!",
        },
    },
}
# es-AR uses neutral Spanish for profile steps
_PROFILE_I18N["es-AR"] = _PROFILE_I18N["es"]

_SUMMARY_LABELS_EN = {
    "title": "📋 *YOUR PROFILE SUMMARY*",
    "stage_name": "🎭 Stage name",
    "age": "🎂 Age",
    "from": "🌎 From",
    "ethnicity": "👤 Ethnicity",
    "hair": "💇 Hair",
    "body": "💪 Body",
    "features": "✨ Features",
    "face_tease": "📸 Face in tease",
    "face_explicit": "🔞 Face in explicit",
    "will_do": "✅ Will do",
    "wont_do": "🚫 Won't do",
    "locations": "📍 Locations",
    "wardrobe": "👗 Wardrobe",
    "personality": "💬 Personality",
    "speaking": "🗣️ Speaking style",
    "complete": "✅ Profile complete!",
}


def get_i18n(lang: str) -> Optional[dict]:
    """Return translation dict for lang (exact match, then base language, then None)."""
    if lang in _PROFILE_I18N:
        return _PROFILE_I18N[lang]
    base = lang.split("-")[0]
    return _PROFILE_I18N.get(base)


def get_step(idx: int, lang: str = "en") -> Optional[dict]:
    if not (0 <= idx < TOTAL_STEPS):
        return None
    step = dict(PROFILE_STEPS[idx])  # shallow copy — never mutate original
    i18n = get_i18n(lang)
    if not i18n:
        return step
    key = step["key"]
    q = i18n.get("questions", {}).get(key)
    if q:
        step["question"] = q
    b = i18n.get("buttons", {}).get(key)
    if b:
        step["button_text"] = b
    t_opts = i18n.get("options", {}).get(key)
    if t_opts:
        step["translated_options"] = t_opts
    return step


def build_keyboard(options: list, translated_labels: list = None, multi_selected: list = None):
    """Build an InlineKeyboardMarkup-compatible structure.

    callback_data always uses the English original option text so handler logic
    (face Yes/No detection, Done ✅ detection, phone ⌨️ detection) never breaks.
    Only the visible button label is translated.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for r_idx, row in enumerate(options):
        btn_row = []
        for c_idx, opt in enumerate(row):
            if translated_labels:
                try:
                    label = translated_labels[r_idx][c_idx]
                except (IndexError, TypeError):
                    label = opt
            else:
                label = opt
            # multi-select checkmark compares against English originals stored in session
            if multi_selected and opt in multi_selected:
                label = f"✅ {label}"
            btn_row.append(InlineKeyboardButton(label, callback_data=f"profile_{opt}"))
        rows.append(btn_row)
    return InlineKeyboardMarkup(rows)


def profile_summary(profile: dict, lang: str = "en") -> str:
    """Generate a human-readable summary of collected profile data."""
    i18n = get_i18n(lang)
    lbl = {**_SUMMARY_LABELS_EN, **(i18n.get("summary", {}) if i18n else {})}
    lines = [
        lbl["title"],
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"{lbl['stage_name']}: {profile.get('stage_name', '?')}",
        f"{lbl['age']}: {profile.get('age', '?')}",
        f"{lbl['from']}: {profile.get('stated_location', '?')}",
        "",
        f"{lbl['ethnicity']}: {profile.get('ethnicity', '?')}",
        f"{lbl['hair']}: {profile.get('hair_color', '?')}, {profile.get('hair_length', '?')}",
        f"{lbl['body']}: {profile.get('body_type', '?')}, {profile.get('height', '?')}",
        f"{lbl['features']}: {profile.get('notable_features', 'none')}",
        "",
        f"{lbl['face_tease']}: {profile.get('face_in_tease', '?')}",
        f"{lbl['face_explicit']}: {profile.get('face_in_explicit', '?')}",
        "",
        f"{lbl['will_do']}: {profile.get('will_do', '?')}",
        f"{lbl['wont_do']}: {profile.get('wont_do', '?')}",
        "",
        f"{lbl['locations']}: {profile.get('shooting_locations', '?')}",
        f"{lbl['wardrobe']}: {profile.get('wardrobe', '?')}",
        "",
        f"{lbl['personality']}: {profile.get('natural_personality', '?')}",
        f"{lbl['speaking']}: {profile.get('natural_speaking_style', '?')}",
    ]
    return "\n".join(lines)


async def save_profile_to_supabase(telegram_id: int, stage_name: str, profile: dict) -> bool:
    """Save completed profile to Supabase models table."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from persistence.supabase_client import get_client
        db = get_client()

        # Upsert by telegram_id
        data = {
            "telegram_id": telegram_id,
            "stage_name": stage_name,
            "profile_json": profile,
            "onboarding_complete": True,
            "is_active": False,  # Activated when she's live on platform
        }
        # Check if record exists first (upsert requires a unique constraint on telegram_id)
        existing = db.table("models").select("id").eq("telegram_id", telegram_id).execute()
        if existing.data:
            db.table("models").update(data).eq("telegram_id", telegram_id).execute()
        else:
            db.table("models").insert(data).execute()
        logger.info(f"Profile saved for TG {telegram_id}: {stage_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to save profile: {e}")
        return False
