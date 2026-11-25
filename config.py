import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "instance" / "tvarkarastis.db"
UPLOAD_DIR = BASE_DIR / "instance" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Paprastas el. pašto formato tikrinimas: kažkas@kažkas.kažkas
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Vaidmenys (RBAC): raktas duomenų bazėje -> pavadinimas sąsajoje
ROLES = {
    "employee": "Darbuotojas",
    "manager": "Vadovas",
    "hr": "Personalo specialistas",
    "admin": "Administratorius",
}
DEFAULT_ROLE = "employee"

# Senos (ankstesnės versijos) vaidmenų reikšmės, kurias konvertuojame
LEGACY_ROLES = {
    "adminas": "admin",
    "pamainu vadovas": "manager",
    "darbotojas": "employee",
}

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
MAX_FILES = 5

REQUEST_TYPES = {
    "vacation": "Atostogos",
    "sick": "Nedarbingumas (liga)",
    "personal": "Asmeniniai reikalai",
    "other": "Kita neatvykimo priežastis",
}

REQUEST_STATUSES = {
    "submitted": "Pateiktas",
    "approved": "Patvirtintas",
    "rejected": "Atmestas",
}

REQUIRED_MSG = "Šis laukas privalomas."


DAY_NAMES = ["Pirmadienis", "Antradienis", "Trečiadienis", "Ketvirtadienis",
             "Penktadienis", "Šeštadienis", "Sekmadienis"]

DAY_SHORT = ["Pir", "Ant", "Tre", "Ket", "Pen", "Šeš", "Sek"]

MONTHS_GENITIVE = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
                   "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

MONTHS_NOMINATIVE = ["Sausis", "Vasaris", "Kovas", "Balandis", "Gegužė", "Birželis",
                     "Liepa", "Rugpjūtis", "Rugsėjis", "Spalis", "Lapkritis", "Gruodis"]

# Pamainų tipai: raktas -> (pavadinimas, pradžia, pabaiga)
SHIFT_TYPES = {
    "day":     ("Dieninė",   "06:00", "14:00"),
    "evening": ("Vakarinė",  "14:00", "22:00"),
    "night":   ("Naktinė",   "22:00", "06:00"),
}

# Savaičių šablonai (demonstraciniai): [Pir, Ant, Tre, Ket, Pen, Šeš, Sek], None = poilsio diena.
# Šablonai kartojasi: ši savaitė = 1-as, kita = 2-as, praėjusi = 3-ias ir t. t.
WEEK_PATTERNS = [
    ["day", "day", "evening", None, "evening", "night", None],
    [None, "day", "day", "day", "evening", None, None],
    ["night", "night", None, None, "evening", "evening", None],
]

SCHEDULE_VIEWS = ("month", "week")   # mėnesio tinklelis arba savaitės sąrašas
MAX_WEEK_OFFSET = 8
MAX_MONTH_OFFSET = 6

DEMO_ANNOUNCEMENTS = [
    {"tag": "Svarbu", "color": "amber",
     "title": "Atnaujintas lapkričio tvarkaraštis",
     "text": "Lapkričio mėnesio pamainų grafikas jau paskelbtas. Prašome jį peržiūrėti.",
     "time": "Prieš 2 val."},
    {"tag": "Naujiena", "color": "indigo",
     "title": "Prašymų teikimas per sistemą",
     "text": "Atostogų ir nedarbingumo prašymus nuo šiol teikite čia, o ne per žinučių programėles.",
     "time": "Vakar"},
    {"tag": "Primenama", "color": "green",
     "title": "Prieinamumo pateikimas",
     "text": "Nurodykite savo galimas darbo dienas kitam mėnesiui iki šio penktadienio.",
     "time": "Prieš 3 d."},
]


