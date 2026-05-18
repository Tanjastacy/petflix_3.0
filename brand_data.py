BRAND_CATEGORIES = [
    ("Pet-Brands", "Pet-Brands", ""),
    ("Owner-Brands", "Owner-Brands", ""),
    ("Forced-Brands", "Forced-Brands", "Nur Owner können diese ihren Pets aufdrücken."),
    ("Shame-Brands", "Shame-Brands", "Für alle, die digitale Selbstachtung für überschätzt halten."),
    ("Legendary-Brands", "Legendary-Brands", ""),
]


DEFAULT_BRANDS = [
    ("Coin-Owned Creature", "Pet-Brands", 500, "self"),
    ("Premium Property", "Pet-Brands", 750, "self"),
    ("Leashed But Loud", "Pet-Brands", 750, "self"),
    ("Property With Attitude", "Pet-Brands", 1000, "self"),
    ("Bought, Not Broken", "Pet-Brands", 1000, "self"),
    ("Too Expensive To Own", "Pet-Brands", 1500, "self"),
    ("Dignity On Cooldown", "Pet-Brands", 1500, "self"),
    ("Pretty Little Problem", "Pet-Brands", 1500, "self"),
    ("Leashed But Untamed", "Pet-Brands", 2000, "self"),
    ("Owner’s Worst Investment", "Pet-Brands", 2500, "self"),
    ("The Leash Holder", "Owner-Brands", 1000, "owner"),
    ("Cold Command", "Owner-Brands", 1500, "owner"),
    ("Owner With Consequences", "Owner-Brands", 2000, "owner"),
    ("Certified Control Issue", "Owner-Brands", 2000, "owner"),
    ("The Pet Collector", "Owner-Brands", 2500, "owner"),
    ("The Collar Capitalist", "Owner-Brands", 3000, "owner"),
    ("No Ethics, Just Coins", "Owner-Brands", 3000, "owner"),
    ("Spends Coins To Feel Something", "Owner-Brands", 4000, "owner"),
    ("The Final Command", "Owner-Brands", 7500, "owner"),
    ("Admin Approved Menace", "Owner-Brands", 10000, "owner"),
    ("Gift From My Owner, Sadly", "Forced-Brands", 1000, "forced"),
    ("Owner Picked This, Not Me", "Forced-Brands", 1000, "forced"),
    ("Decorated Against My Will", "Forced-Brands", 1500, "forced"),
    ("This Was Not My Choice", "Forced-Brands", 1500, "forced"),
    ("My Owner Thinks This Is Funny", "Forced-Brands", 2000, "forced"),
    ("Paid Humiliation Package", "Forced-Brands", 2500, "forced"),
    ("Owner’s Joke, My Problem", "Forced-Brands", 2500, "forced"),
    ("Petflix Hostage Label", "Forced-Brands", 3000, "forced"),
    ("My Owner Needs A Hobby", "Forced-Brands", 3000, "forced"),
    ("Branded By Bad Taste", "Forced-Brands", 3500, "forced"),
    ("Professional Disappointment", "Shame-Brands", 500, "shame"),
    ("Premium Embarrassment", "Shame-Brands", 750, "shame"),
    ("Walking Receipt", "Shame-Brands", 750, "shame"),
    ("No Refund Available", "Shame-Brands", 1000, "shame"),
    ("Public Shame Upgrade", "Shame-Brands", 1500, "shame"),
    ("Personality Patch Failed", "Shame-Brands", 1500, "shame"),
    ("Still Loading Dignity", "Shame-Brands", 1500, "shame"),
    ("Human Error In Pet Form", "Shame-Brands", 2000, "shame"),
    ("Proof Coins Were Misused", "Shame-Brands", 2500, "shame"),
    ("Admin Should Have Stopped This", "Shame-Brands", 3000, "shame"),
    ("Black Collar Asset", "Legendary-Brands", 5000, "legendary"),
    ("Command Locked", "Legendary-Brands", 5000, "legendary"),
    ("Private Property Protocol", "Legendary-Brands", 6000, "legendary"),
    ("The Owner’s Mark", "Legendary-Brands", 6000, "legendary"),
    ("Control Tagged", "Legendary-Brands", 7000, "legendary"),
    ("Collar Protocol Active", "Legendary-Brands", 7500, "legendary"),
    ("Bound And Branded", "Legendary-Brands", 8000, "legendary"),
    ("Claimed In Black", "Legendary-Brands", 9000, "legendary"),
    ("Obedience Pending", "Legendary-Brands", 10000, "legendary"),
    ("Public Shame Upgrade Deluxe", "Legendary-Brands", 12000, "legendary"),
]


BRAND_BUY_LINES = [
    '{user} kauft sich die Brandmarke "{brand}" für {price} Coins. Selbstachtung wäre günstiger gewesen, aber offenbar weniger sichtbar.',
    '{user} trägt jetzt "{brand}". Ob das hilft? Nein. Aber es sieht teuer aus.',
    '{user} hat {price} Coins für "{brand}" ausgegeben. Finanzielle Selbstkontrolle wurde offiziell beerdigt.',
    '"{brand}" gehört jetzt {user}. Die Gruppe wird gebeten, angemessen zu urteilen.',
    '{user} hat sich "{brand}" gekauft. Ein kleiner Schritt für den Bot, ein großer Rückschritt für die Würde.',
]


BRAND_SET_LINES = [
    '{user} trägt jetzt "{brand}". Tragisch, aber konsequent.',
    'Aktive Brandmarke geändert zu "{brand}". Die Außenwirkung bleibt fragwürdig.',
    '{user} präsentiert sich ab jetzt als "{brand}". Niemand hat gefragt, aber hier sind wir.',
]


BRAND_PET_LINES = [
    '{owner} kauft {pet} die Brandmarke "{brand}". {pet} wurde nicht gefragt. Das war vermutlich der Punkt.',
    '{pet} trägt jetzt "{brand}", bezahlt von {owner}. Freiwilligkeit wurde kurz geprüft und dann ignoriert.',
    '{owner} hat {pet} offiziell mit "{brand}" dekoriert. Geschmack bleibt weiterhin nicht strafbar, leider.',
    '{pet} wurde von {owner} mit "{brand}" markiert. Die Würde kann später gegen Coins zurückgekauft werden.',
    '{owner} hat {price} Coins bezahlt, damit {pet} jetzt "{brand}" tragen muss. Telegram war ein Fehler, aber wenigstens ein unterhaltsamer.',
]


BRAND_REMOVE_LINES = [
    '{pet} hat "{brand}" abgelegt und {price} Coins bezahlt. Würde zurückgekauft. Gebraucht, aber funktional.',
    '{pet} hat sich von "{brand}" freigekauft. Der Stolz war teuer, aber immerhin wieder da.',
    '{pet} zahlt {price} Coins, um "{brand}" loszuwerden. Der Owner wird gebeten, normal zu reagieren. Wird er nicht.',
    '"{brand}" wurde entfernt. {pet} hat damit bewiesen, dass Scham käuflich ist.',
    '{pet} kauft sich frei. Kurz dachte man, hier gäbe es Selbstbestimmung. Süß.',
]


VOLUNTARY_BRAND_TYPES = {"self", "owner", "shame", "legendary"}
FORCED_BRAND_TYPES = {"forced", "shame"}
