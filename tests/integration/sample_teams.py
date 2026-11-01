"""M-B teams from public Poképastes, used only by real engine tests."""

OUR_SNAPSHOT = {
    "pokemon": [
        {
            "rawBlock": """Whimsicott @ Focus Sash
Ability: Prankster
Level: 50
EVs: 1 Def / 32 SpA / 1 SpD / 32 Spe
Timid Nature
- Moonblast
- Endeavor
- Encore
- Tailwind""",
        },
        {
            "rawBlock": """Floette-Eternal (F) @ Floettite
Ability: Flower Veil
Level: 50
EVs: 2 HP / 32 SpA / 32 Spe
Timid Nature
- Dazzling Gleam
- Moonblast
- Protect
- Light of Ruin""",
        },
        {
            "rawBlock": """Sneasler @ White Herb
Ability: Unburden
Level: 50
EVs: 32 Atk / 2 Def / 32 Spe
Adamant Nature
- Dire Claw
- Close Combat
- Fake Out
- Rock Slide""",
        },
        {
            "rawBlock": """Basculegion (M) @ Colbur Berry
Ability: Adaptability
Level: 50
EVs: 32 Atk / 2 Def / 32 Spe
Adamant Nature
- Wave Crash
- Last Respects
- Protect
- Aqua Jet""",
        },
        {
            "rawBlock": """Kleavor @ Life Orb
Ability: Sharpness
Level: 50
EVs: 2 HP / 32 Atk / 4 Def / 28 Spe
Jolly Nature
- X-Scissor
- Stone Axe
- Protect
- Night Slash""",
        },
        {
            "rawBlock": """Chandelure @ Chandelurite
Ability: Flash Fire
Level: 50
EVs: 30 HP / 15 SpD / 21 Spe
Timid Nature
- Heat Wave
- Shadow Ball
- Protect
- Taunt""",
        },
    ]
}

OPPONENT_SNAPSHOT = {
    "pokemon": [
        {
            "rawBlock": """Aerodactyl (M) @ Aerodactylite
Ability: Unnerve
EVs: 16 HP / 13 Atk / 5 SpD / 32 Spe
Jolly Nature
- Rock Slide
- Dual Wingbeat
- Ice Fang
- Tailwind""",
        },
        {
            "rawBlock": """Raichu (M) @ Raichunite Y
Ability: Lightning Rod
EVs: 32 HP / 3 Def / 2 SpA / 5 SpD / 24 Spe
Timid Nature
- Zap Cannon
- Focus Blast
- Fake Out
- Protect""",
        },
        {
            "rawBlock": """Garchomp (M) @ Life Orb
Ability: Rough Skin
Level: 50
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Dragon Claw
- Earthquake
- Rock Slide
- Protect""",
        },
        {
            "rawBlock": """Sylveon (M) @ Fairy Feather
Ability: Pixilate
Level: 50
Modest Nature
- Hyper Voice
- Hyper Beam
- Quick Attack
- Detect""",
        },
        {
            "rawBlock": """Meowscarada (M) @ Choice Scarf
Ability: Protean
EVs: 1 HP / 32 Atk / 1 Def / 32 Spe
Jolly Nature
- Flower Trick
- Throat Chop
- Triple Axel
- Low Kick""",
        },
        {
            "rawBlock": """Kingambit (F) @ Focus Sash
Ability: Defiant
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Kowtow Cleave
- Iron Head
- Low Kick
- Sucker Punch""",
        },
    ]
}

# Kept for fixture-only tests that do not need distinct teams.
SAMPLE_SNAPSHOT = OUR_SNAPSHOT
