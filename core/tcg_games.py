"""
TCG Game Configuration - Centralized configuration for Trading Card Game detection.

This module provides a clean, extensible architecture for detecting and categorizing
TCG games from marketplace listings. It supports both Japanese and English title matching,
as well as professional grading detection (PSA, BGS, CGC, etc.).

Supported Games:
    - Pokemon Card Game (ポケモンカード)
    - Yu-Gi-Oh! (遊戯王)
    - One Piece Card Game (ワンピースカード)
    - Magic: The Gathering (MTG)
    - Weiss Schwarz (ヴァイスシュヴァルツ)
    - Dragon Ball Super Card Game
    - Digimon Card Game (デジモンカード)
    - Cardfight!! Vanguard (ヴァンガード)
    - Union Arena (ユニオンアリーナ)
    - Duel Masters (デュエルマスターズ)

Supported Grading Companies:
    - PSA (Professional Sports Authenticator)
    - BGS/BVG (Beckett Grading Services)
    - CGC (Certified Guaranty Company)
    - SGC (Sportscard Guaranty Corporation)
    - ARS (Ace Grading)
    - And others (AGS, GMA, ISA, MNT, TAG)

Usage:
    from core.tcg_games import TCGGameDetector, TCGGame, GradingCompany

    detector = TCGGameDetector()

    # Detect game from title
    game = detector.detect_game("ポケモンカード ピカチュウex SAR sv2a 165/165")
    # Returns: TCGGame.POKEMON

    # Extract card info with game-specific patterns (includes grading info)
    card_info = detector.extract_card_info("ピカチュウex PSA10 [SV2a 165/165]", TCGGame.POKEMON)
    # Returns: {
    #     "game": "POKEMON",
    #     "set_code": "SV2A",
    #     "card_number": "165",
    #     "rarity": None,
    #     "language": "JP",
    #     "is_graded": True,
    #     "grading_company": "PSA",
    #     "grade": 10.0,
    #     "grade_qualifier": None,
    #     "cert_number": None
    # }

    # Get game config
    config = detector.get_game_config(TCGGame.POKEMON)
    # Returns: TCGGameConfig with display_name, keywords, patterns, etc.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Pattern, Set, Tuple, Union
import re


# ============================================================================
# GRADING COMPANY CONFIGURATION
# ============================================================================


class GradingCompany(str, Enum):
    """
    Enumeration of professional card grading companies.

    String enum allows direct use in database fields and JSON serialization.
    Each company has different grading scales and conventions.
    """
    PSA = "PSA"           # Professional Sports Authenticator (1-10 scale)
    BGS = "BGS"           # Beckett Grading Services (1-10 with subgrades, half points)
    BVG = "BVG"           # Beckett Vintage Grading (vintage cards)
    CGC = "CGC"           # Certified Guaranty Company (1-10 with subgrades)
    SGC = "SGC"           # Sportscard Guaranty Corporation (1-10 scale)
    ARS = "ARS"           # Ace Grading (1-10 scale, popular in Japan)
    AGS = "AGS"           # Automated Grading Services
    GMA = "GMA"           # GMA Grading (1-10 scale)
    ISA = "ISA"           # ISA Grading
    MNT = "MNT"           # MNT Grading
    TAG = "TAG"           # TAG Grading
    UNKNOWN = "UNKNOWN"   # Graded but company not identified


@dataclass
class GradingCompanyConfig:
    """
    Configuration for a grading company including detection patterns and grade scales.

    Attributes:
        company: GradingCompany enum value
        display_name: Full company name
        keywords: Keywords for detecting this company in titles
        grade_scale: Tuple of (min_grade, max_grade)
        supports_half_grades: Whether company uses .5 grades (e.g., BGS 9.5)
        supports_subgrades: Whether company provides subgrades (centering, corners, etc.)
        grade_pattern: Regex pattern for extracting grade value
        cert_pattern: Regex pattern for extracting certification number
        qualifiers: Grade qualifiers used by this company (e.g., "OC" for off-center)
    """
    company: GradingCompany
    display_name: str
    keywords: Set[str] = field(default_factory=set)
    grade_scale: Tuple[float, float] = (1.0, 10.0)
    supports_half_grades: bool = False
    supports_subgrades: bool = False
    grade_pattern: str = ""
    cert_pattern: str = ""
    qualifiers: Set[str] = field(default_factory=set)


# Grading company configurations
PSA_CONFIG = GradingCompanyConfig(
    company=GradingCompany.PSA,
    display_name="Professional Sports Authenticator",
    keywords={"psa", "psa鑑定", "psa評価"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=False,
    supports_subgrades=False,
    # Matches: PSA10, PSA 10, PSA-10, PSA（10）, PSA(10), psa鑑定 10
    grade_pattern=r'psa[\s\-]*(?:鑑定|評価)?[\s]*[（\(]?(\d{1,2})[）\)]?',
    # PSA cert numbers are typically 8-10 digits
    cert_pattern=r'(?:cert|#|番号|認定番号)[\s:：]?(\d{8,10})',
    qualifiers={"OC", "MC", "MK", "PD", "ST"},  # Off-center, Miscut, Marks, Print Defect, Stain
)

BGS_CONFIG = GradingCompanyConfig(
    company=GradingCompany.BGS,
    display_name="Beckett Grading Services",
    keywords={"bgs", "beckett", "ベケット", "bgs鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=True,
    # Matches: BGS9.5, BGS 9.5, BGS-10, BGS（9.5）, bgs鑑定 9.5
    grade_pattern=r'bgs[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{7,10})',
    qualifiers={"PRISTINE", "BLACK LABEL", "GOLD LABEL", "SILVER LABEL"},
)

BVG_CONFIG = GradingCompanyConfig(
    company=GradingCompany.BVG,
    display_name="Beckett Vintage Grading",
    keywords={"bvg", "beckett vintage"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=True,
    grade_pattern=r'bvg[\s\-]?[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{7,10})',
    qualifiers=set(),
)

CGC_CONFIG = GradingCompanyConfig(
    company=GradingCompany.CGC,
    display_name="Certified Guaranty Company",
    keywords={"cgc", "cgc鑑定", "cgcカード"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=True,
    # Matches: CGC9.5, CGC 10, CGC-9, cgc鑑定 9.5
    grade_pattern=r'cgc[\s\-]*(?:鑑定|カード)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{7,12})',
    qualifiers={"PRISTINE", "PERFECT"},
)

SGC_CONFIG = GradingCompanyConfig(
    company=GradingCompany.SGC,
    display_name="Sportscard Guaranty Corporation",
    keywords={"sgc", "sgc鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=False,
    supports_subgrades=False,
    # Matches: SGC10, SGC 9, SGC-10, sgc鑑定 10
    grade_pattern=r'sgc[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2})[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{7,10})',
    qualifiers={"PRISTINE", "GOLD LABEL"},
)

ARS_CONFIG = GradingCompanyConfig(
    company=GradingCompany.ARS,
    display_name="Ace Grading",
    keywords={"ars", "ace", "ace鑑定", "ars鑑定", "エース"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=True,
    # Matches: ARS10, ARS 9.5, ARS-10, ace鑑定 9, ace 10
    grade_pattern=r'(?:ars|ace)[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{6,10})',
    qualifiers=set(),
)

AGS_CONFIG = GradingCompanyConfig(
    company=GradingCompany.AGS,
    display_name="Automated Grading Services",
    keywords={"ags", "ags鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=False,
    grade_pattern=r'ags[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{6,10})',
    qualifiers=set(),
)

GMA_CONFIG = GradingCompanyConfig(
    company=GradingCompany.GMA,
    display_name="GMA Grading",
    keywords={"gma", "gma鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=False,
    supports_subgrades=False,
    grade_pattern=r'gma[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2})[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{6,10})',
    qualifiers=set(),
)

ISA_CONFIG = GradingCompanyConfig(
    company=GradingCompany.ISA,
    display_name="ISA Grading",
    keywords={"isa", "isa鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=False,
    grade_pattern=r'isa[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{6,10})',
    qualifiers=set(),
)

MNT_CONFIG = GradingCompanyConfig(
    company=GradingCompany.MNT,
    display_name="MNT Grading",
    keywords={"mnt", "mnt鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=False,
    grade_pattern=r'mnt[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{6,10})',
    qualifiers=set(),
)

TAG_CONFIG = GradingCompanyConfig(
    company=GradingCompany.TAG,
    display_name="TAG Grading",
    keywords={"tag", "tag鑑定"},
    grade_scale=(1.0, 10.0),
    supports_half_grades=True,
    supports_subgrades=False,
    # Matches: TAG10, TAG 9.5, tag鑑定 9
    grade_pattern=r'tag[\s\-]*(?:鑑定)?[\s]*[（\(]?(\d{1,2}(?:\.\d)?)[）\)]?',
    cert_pattern=r'(?:cert|#|番号)[\s:：]?(\d{6,10})',
    qualifiers=set(),
)

# All grading company configurations
ALL_GRADING_CONFIGS: Dict[GradingCompany, GradingCompanyConfig] = {
    GradingCompany.PSA: PSA_CONFIG,
    GradingCompany.BGS: BGS_CONFIG,
    GradingCompany.BVG: BVG_CONFIG,
    GradingCompany.CGC: CGC_CONFIG,
    GradingCompany.SGC: SGC_CONFIG,
    GradingCompany.ARS: ARS_CONFIG,
    GradingCompany.AGS: AGS_CONFIG,
    GradingCompany.GMA: GMA_CONFIG,
    GradingCompany.ISA: ISA_CONFIG,
    GradingCompany.MNT: MNT_CONFIG,
    GradingCompany.TAG: TAG_CONFIG,
}


@dataclass
class GradingInfo:
    """
    Extracted grading information from a listing title.

    Attributes:
        is_graded: Whether the card is professionally graded
        company: Grading company (None if not graded or unknown)
        grade: Numeric grade value (None if not detected)
        grade_qualifier: Grade qualifier like "OC", "BLACK LABEL" (None if none)
        cert_number: Certification number (None if not detected)
    """
    is_graded: bool = False
    company: Optional[GradingCompany] = None
    grade: Optional[float] = None
    grade_qualifier: Optional[str] = None
    cert_number: Optional[str] = None

    def to_dict(self) -> Dict[str, Union[bool, str, float, None]]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_graded": self.is_graded,
            "grading_company": self.company.value if self.company else None,
            "grade": self.grade,
            "grade_qualifier": self.grade_qualifier,
            "cert_number": self.cert_number,
        }


class GradingDetector:
    """
    Detects professional grading information from listing titles.

    Supports detection of:
    - Grading company (PSA, BGS, CGC, SGC, ARS, etc.)
    - Grade value (numeric, supports half grades like 9.5)
    - Grade qualifiers (OC, BLACK LABEL, PRISTINE, etc.)
    - Certification numbers

    Example:
        detector = GradingDetector()

        # Detect grading from title
        info = detector.detect_grading("ポケモン ピカチュウ PSA10 認定番号12345678")
        # Returns: GradingInfo(
        #     is_graded=True,
        #     company=GradingCompany.PSA,
        #     grade=10.0,
        #     grade_qualifier=None,
        #     cert_number="12345678"
        # )
    """

    # General patterns for detecting graded cards without specific company
    GENERAL_GRADED_KEYWORDS = {
        "鑑定", "鑑定品", "graded", "slab", "slabbed",
        "ケース入り", "鑑定済", "鑑定済み",
    }

    def __init__(self):
        """Initialize the detector with compiled regex patterns."""
        self._compiled_patterns: Dict[GradingCompany, Dict[str, Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for all grading companies."""
        for company, config in ALL_GRADING_CONFIGS.items():
            self._compiled_patterns[company] = {
                "grade": re.compile(config.grade_pattern, re.IGNORECASE),
                "cert": re.compile(config.cert_pattern, re.IGNORECASE) if config.cert_pattern else None,
            }

    def detect_grading(self, title: str) -> GradingInfo:
        """
        Detect grading information from a listing title.

        Args:
            title: Product listing title

        Returns:
            GradingInfo with detected grading details
        """
        if not title:
            return GradingInfo()

        title_lower = title.lower()
        result = GradingInfo()

        # Collect all potential matches and score them
        # Prefer matches that have a grade value extracted
        candidates: List[Tuple[int, GradingInfo]] = []

        # Try to detect specific grading company and grade
        for company, config in ALL_GRADING_CONFIGS.items():
            # Check if any keyword matches
            # Use word boundary matching for short ASCII keywords (3 chars or less) to avoid
            # false positives like "tag" matching "vintage"
            # Allow numbers after the keyword (e.g., PSA10, BGS9.5)
            # Japanese keywords don't need word boundaries since Japanese doesn't use spaces
            keyword_match = False
            for kw in config.keywords:
                is_ascii = all(ord(c) < 128 for c in kw)
                if is_ascii and len(kw) <= 3:
                    # Use word boundary at start, allow number or word boundary at end
                    # This allows "PSA10" but not "vintage" matching "tag"
                    pattern = re.compile(r'\b' + re.escape(kw) + r'(?=\d|\b)', re.IGNORECASE)
                    if pattern.search(title):
                        keyword_match = True
                        break
                else:
                    # Direct substring match for longer keywords or Japanese keywords
                    if kw in title_lower:
                        keyword_match = True
                        break
            if not keyword_match:
                continue

            candidate = GradingInfo(is_graded=True, company=company)
            score = 1  # Base score for keyword match

            # Extract grade value
            patterns = self._compiled_patterns[company]
            grade_match = patterns["grade"].search(title_lower)
            if grade_match:
                try:
                    grade_str = grade_match.group(1)
                    grade_value = float(grade_str)
                    # Validate grade is within scale
                    min_grade, max_grade = config.grade_scale
                    if min_grade <= grade_value <= max_grade:
                        candidate.grade = grade_value
                        score += 10  # Strong bonus for having a grade
                except (ValueError, IndexError):
                    pass

            # Extract certification number
            if patterns["cert"]:
                cert_match = patterns["cert"].search(title)
                if cert_match:
                    candidate.cert_number = cert_match.group(1)
                    score += 5  # Bonus for cert number

            # Check for qualifiers (use word boundary matching to avoid false positives)
            for qualifier in config.qualifiers:
                # Use regex with word boundaries for short qualifiers to avoid false matches
                # e.g., avoid matching "ST" in "PRISTINE"
                qualifier_pattern = re.compile(
                    r'\b' + re.escape(qualifier) + r'\b',
                    re.IGNORECASE
                )
                if qualifier_pattern.search(title):
                    candidate.grade_qualifier = qualifier
                    score += 2  # Small bonus for qualifier
                    break

            candidates.append((score, candidate))

        # Return the best candidate (highest score)
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # Check for general grading keywords (graded but company unknown)
        for keyword in self.GENERAL_GRADED_KEYWORDS:
            if keyword in title_lower:
                result.is_graded = True
                result.company = GradingCompany.UNKNOWN
                return result

        return result

    def get_company_config(self, company: GradingCompany) -> Optional[GradingCompanyConfig]:
        """Get configuration for a specific grading company."""
        return ALL_GRADING_CONFIGS.get(company)

    def get_all_companies(self) -> List[GradingCompany]:
        """Get list of all supported grading companies (excluding UNKNOWN)."""
        return [c for c in GradingCompany if c != GradingCompany.UNKNOWN]


# Singleton grading detector instance
_grading_detector: Optional[GradingDetector] = None


def get_grading_detector() -> GradingDetector:
    """Get or create singleton GradingDetector instance."""
    global _grading_detector
    if _grading_detector is None:
        _grading_detector = GradingDetector()
    return _grading_detector


def detect_grading(title: str) -> GradingInfo:
    """
    Convenience function to detect grading from title.

    Args:
        title: Product title

    Returns:
        GradingInfo with detected grading details
    """
    return get_grading_detector().detect_grading(title)


# ============================================================================
# TCG GAME CONFIGURATION
# ============================================================================


class TCGGame(str, Enum):
    """
    Enumeration of supported TCG games.

    String enum allows direct use in database fields and JSON serialization.
    """
    POKEMON = "POKEMON"
    YUGIOH = "YUGIOH"
    ONE_PIECE = "ONE_PIECE"
    MAGIC = "MAGIC"
    WEISS_SCHWARZ = "WEISS_SCHWARZ"
    DRAGON_BALL = "DRAGON_BALL"
    DIGIMON = "DIGIMON"
    VANGUARD = "VANGUARD"
    UNION_ARENA = "UNION_ARENA"
    DUEL_MASTERS = "DUEL_MASTERS"
    UNKNOWN = "UNKNOWN"


@dataclass
class TCGGameConfig:
    """
    Configuration for a single TCG game including detection patterns.

    Attributes:
        game: TCGGame enum value
        display_name_en: English display name
        display_name_jp: Japanese display name
        keywords_jp: Japanese keywords for detection (lowercase matching)
        keywords_en: English keywords for detection (lowercase matching)
        character_keywords: Character/card names unique to this game
        set_code_patterns: Regex patterns for extracting set codes
        card_number_patterns: Regex patterns for extracting card numbers
        rarity_keywords: Mapping of rarity codes to their keywords
        snkrdunk_brand_id: Brand ID for SNKRDUNK marketplace (if applicable)
    """
    game: TCGGame
    display_name_en: str
    display_name_jp: str
    keywords_jp: Set[str] = field(default_factory=set)
    keywords_en: Set[str] = field(default_factory=set)
    character_keywords: Set[str] = field(default_factory=set)
    set_code_patterns: List[str] = field(default_factory=list)
    card_number_patterns: List[str] = field(default_factory=list)
    rarity_keywords: Dict[str, List[str]] = field(default_factory=dict)
    snkrdunk_brand_id: Optional[str] = None


# ============================================================================
# GAME CONFIGURATIONS
# ============================================================================

POKEMON_CONFIG = TCGGameConfig(
    game=TCGGame.POKEMON,
    display_name_en="Pokemon Card Game",
    display_name_jp="ポケモンカードゲーム",
    keywords_jp={
        "ポケモン", "ポケカ", "ポケモンカード",
        "ピカチュウ", "リザードン", "ミュウ", "ミュウツー",
        "イーブイ", "ゲッコウガ", "レックウザ", "ルギア",
    },
    keywords_en={
        "pokemon", "pokémon", "poke", "ptcg",
        "pikachu", "charizard", "mew", "mewtwo",
        "eevee", "greninja", "rayquaza", "lugia",
    },
    character_keywords={
        "ex", "vmax", "vstar", "v", "gx", "tag team",
        "古代", "未来", "テラスタル",
    },
    set_code_patterns=[
        r'\[([A-Za-z]{1,3}\d{1,2}[a-z]?)\s+\d{3}/\d{3}\]',  # [SV2a 165/165]
        r'\[([A-Za-z]{1,3}\d{1,2}[a-z]?)\-?P?\s',  # [SV-P 069] promo
        r'([Ss][Vv]\d{1,2}[a-z]?)',  # SV2a, sv1, SV8a (Scarlet/Violet)
        r'([Ss]\d{1,2}[a-z]?)',      # S8a, s6a (Sword/Shield)
        r'([Mm]\d[a-z]?)',           # M2a (mega expansion)
        r'([Bb][Ww]\d{1,2})',        # BW2 (Black/White)
        r'([Xx][Yy]\d{1,2})',        # XY10 (X/Y)
        r'([Ss][Mm]\d{1,2}[a-z]?)',  # SM12a (Sun/Moon)
        r'([Cc][Pp]\d{1,2})',        # CP3 (concept packs)
    ],
    card_number_patterns=[
        r'\[(?:[A-Za-z]{1,3}\d{1,2}[a-z]?)\s+(\d{3})/\d{3}\]',  # [SV2a 165/165] -> 165
        r'(\d{3})/\d{3}',  # 165/165 format
        r'#(\d{3})',       # #001 format
    ],
    rarity_keywords={
        "SAR": ["SAR", "スペシャルアートレア"],
        "SR": ["SR", "スーパーレア", "super rare"],
        "UR": ["UR", "ウルトラレア", "ultra rare"],
        "AR": ["AR", "アートレア", "art rare"],
        "RR": ["RR", "ダブルレア", "double rare"],
        "R": [" R ", "レア"],  # Space around R to avoid false matches
        "CHR": ["CHR", "キャラクターレア"],
        "CSR": ["CSR", "キャラクタースーパーレア"],
        "PROMO": ["プロモ", "promo", "プロモーション"],
        "SECRET": ["シークレット", "secret"],
    },
    snkrdunk_brand_id="pokemon",
)

YUGIOH_CONFIG = TCGGameConfig(
    game=TCGGame.YUGIOH,
    display_name_en="Yu-Gi-Oh!",
    display_name_jp="遊戯王",
    keywords_jp={
        "遊戯王", "ゆうぎおう", "遊☆戯☆王",
        "ブルーアイズ", "ブラックマジシャン", "デュエリスト",
        "エクゾディア", "オシリス", "オベリスク",
    },
    keywords_en={
        "yugioh", "yu-gi-oh", "ygo",
        "blue-eyes", "dark magician", "exodia",
        "duelist", "konami",
    },
    character_keywords={
        "青眼の白龍", "暗黒騎士ガイア", "真紅眼の黒竜",
    },
    set_code_patterns=[
        r'([A-Z]{2,5}-[A-Z]{2}\d{3})',  # BODE-JP001
        r'([A-Z]{2,5}-[A-Z]{2})',       # BODE-JP (just set code)
        r'([A-Z]{4,5}\d{3})',           # ROTD001
    ],
    card_number_patterns=[
        r'([A-Z]{2,5}-[A-Z]{2})(\d{3})',  # BODE-JP001 -> 001
        r'(\d{3})$',  # Trailing 3-digit number
    ],
    rarity_keywords={
        "UTRA": ["アルティメットレア", "ultimate rare", "レリーフ"],
        "SECRET": ["シークレット", "secret", "シク"],
        "ULTRA": ["ウルトラ", "ultra"],
        "SUPER": ["スーパー", "super"],
        "RARE": ["レア", "rare"],
        "PRISMATIC": ["プリズマ", "prismatic", "プリシク"],
        "COLLECTOR": ["コレクターズ", "collector"],
        "GOLD": ["ゴールド", "gold"],
        "STARLIGHT": ["スターライト", "starlight"],
    },
    snkrdunk_brand_id="yu-gi-oh",
)

ONE_PIECE_CONFIG = TCGGameConfig(
    game=TCGGame.ONE_PIECE,
    display_name_en="One Piece Card Game",
    display_name_jp="ワンピースカードゲーム",
    keywords_jp={
        "ワンピース", "ワンピ", "onepiece",
        "ルフィ", "ゾロ", "ナミ", "サンジ", "ウソップ",
        "チョッパー", "ロビン", "フランキー", "ブルック",
        "ニカ", "ギア5", "海賊王",
    },
    keywords_en={
        "one piece", "onepiece", "optcg",
        "luffy", "zoro", "nami", "sanji",
        "chopper", "robin", "franky", "brook",
        "gear 5", "nika",
    },
    character_keywords={
        "麦わらの一味", "海軍", "王下七武海", "四皇",
    },
    set_code_patterns=[
        r'\[?([Oo][Pp]\d{2})\]?',  # OP01, OP02
        r'\[?([Ss][Tt]\d{2})\]?',  # ST01, ST02 (starter decks)
        r'\[?([Ee][Bb]\d{2})\]?',  # EB01 (extra boosters)
        r'\[?([Pp][Rr][Bb]\d{2})\]?',  # PRB01 (premium boosters)
    ],
    card_number_patterns=[
        r'([Oo][Pp]\d{2})-(\d{3})',  # OP01-001
        r'([Ss][Tt]\d{2})-(\d{3})',  # ST01-001
        r'-(\d{3})$',  # Trailing -001
    ],
    rarity_keywords={
        "L": ["L", "リーダー", "leader"],
        "SEC": ["SEC", "シークレット"],
        "SR": ["SR", "スーパーレア"],
        "R": [" R ", "レア"],
        "UC": ["UC", "アンコモン"],
        "C": [" C ", "コモン"],
        "SP": ["SP", "スペシャル", "special"],
        "MANGA": ["漫画", "コミパラ", "comic"],
        "ALT": ["パラレル", "parallel", "alt"],
    },
    snkrdunk_brand_id="onepiece",
)

MAGIC_CONFIG = TCGGameConfig(
    game=TCGGame.MAGIC,
    display_name_en="Magic: The Gathering",
    display_name_jp="マジック・ザ・ギャザリング",
    keywords_jp={
        "マジック", "ギャザリング", "mtg",
        "プレインズウォーカー", "黒蓮",
    },
    keywords_en={
        "magic", "mtg", "gathering", "wizards",
        "planeswalker", "commander", "edh",
        "black lotus", "mox",
    },
    character_keywords={
        "liliana", "jace", "chandra", "nicol bolas",
    },
    set_code_patterns=[
        r'\[?([A-Z]{3})\]?',  # BRO, DMU, ONE (3-letter codes)
        r'\[?([A-Z]{3,4})\]?',  # WOTC set codes
    ],
    card_number_patterns=[
        r'(\d{1,3})/(\d{1,3})',  # 001/280
        r'#(\d{1,3})',  # #001
    ],
    rarity_keywords={
        "MYTHIC": ["mythic", "神話レア", "神話"],
        "RARE": ["rare", "レア"],
        "UNCOMMON": ["uncommon", "アンコモン"],
        "COMMON": ["common", "コモン"],
        "FOIL": ["foil", "フォイル", "光る"],
        "BORDERLESS": ["ボーダーレス", "borderless"],
        "SHOWCASE": ["ショーケース", "showcase"],
        "EXTENDED": ["拡張アート", "extended art"],
    },
    snkrdunk_brand_id="mtg",
)

WEISS_SCHWARZ_CONFIG = TCGGameConfig(
    game=TCGGame.WEISS_SCHWARZ,
    display_name_en="Weiss Schwarz",
    display_name_jp="ヴァイスシュヴァルツ",
    keywords_jp={
        "ヴァイス", "シュヴァルツ", "ヴァイスシュヴァルツ",
        "ws", "weiss",
    },
    keywords_en={
        "weiss", "schwarz", "ws", "weiβ",
        "bushiroad",
    },
    character_keywords=set(),  # Many anime franchises, hard to list
    set_code_patterns=[
        r'([A-Z]{2,4}/[A-Z]\d{2}[A-Z]?)',  # BD/W63, SAO/S71
        r'([A-Z]{2,4}-[A-Z]\d{2})',  # BD-W63
    ],
    card_number_patterns=[
        r'([A-Z]{2,4}/[A-Z]\d{2}[A-Z]?)-(\d{2,3})',  # BD/W63-001
        r'-(\d{2,3})$',
    ],
    rarity_keywords={
        "SP": ["SP", "サイン", "sign"],
        "SSP": ["SSP", "スーパースペシャル"],
        "SEC": ["SEC", "シークレット"],
        "RRR": ["RRR", "トリプルレア"],
        "SR": ["SR", "スーパーレア"],
        "RR": ["RR", "ダブルレア"],
        "R": [" R ", "レア"],
        "U": [" U ", "アンコモン"],
        "C": [" C ", "コモン"],
        "PR": ["PR", "プロモ"],
    },
    snkrdunk_brand_id="weis-schwarz",
)

DRAGON_BALL_CONFIG = TCGGameConfig(
    game=TCGGame.DRAGON_BALL,
    display_name_en="Dragon Ball Super Card Game",
    display_name_jp="ドラゴンボールスーパーカードゲーム",
    keywords_jp={
        "ドラゴンボール", "ドラゴボ", "db", "dbh",
        "悟空", "ベジータ", "フリーザ", "セル",
        "スーパーサイヤ人", "超サイヤ人",
    },
    keywords_en={
        "dragon ball", "dragonball", "dbs", "dbscg",
        "goku", "vegeta", "frieza", "cell",
        "super saiyan", "ssj",
    },
    character_keywords={
        "孫悟空", "孫悟飯", "トランクス", "ブロリー",
    },
    set_code_patterns=[
        r'([Bb][Tt]\d{1,2})',  # BT1, BT15
        r'([Pp]\d{3})',  # P001 (promos)
        r'([Ss][Dd]\d{1,2})',  # SD1 (starter decks)
    ],
    card_number_patterns=[
        r'([Bb][Tt]\d{1,2})-(\d{3})',  # BT1-001
        r'-(\d{3})$',
    ],
    rarity_keywords={
        "SCR": ["SCR", "シークレット"],
        "SPR": ["SPR", "スペシャル"],
        "SR": ["SR", "スーパーレア"],
        "R": [" R ", "レア"],
        "UC": ["UC", "アンコモン"],
        "C": [" C ", "コモン"],
    },
    snkrdunk_brand_id=None,  # Not on SNKRDUNK
)

DIGIMON_CONFIG = TCGGameConfig(
    game=TCGGame.DIGIMON,
    display_name_en="Digimon Card Game",
    display_name_jp="デジモンカードゲーム",
    keywords_jp={
        "デジモン", "デジカ", "digimon",
        "アグモン", "ガブモン", "オメガモン",
    },
    keywords_en={
        "digimon", "dcg",
        "agumon", "gabumon", "omegamon", "omnimon",
    },
    character_keywords={
        "ウォーグレイモン", "メタルガルルモン",
    },
    set_code_patterns=[
        r'([Bb][Tt]\d{1,2})',  # BT1, BT15
        r'([Ss][Tt]\d{1,2})',  # ST1 (starter)
        r'([Ee][Xx]\d{1,2})',  # EX1 (expansion)
    ],
    card_number_patterns=[
        r'([Bb][Tt]\d{1,2})-(\d{3})',  # BT1-001
        r'-(\d{3})$',
    ],
    rarity_keywords={
        "SEC": ["SEC", "シークレット"],
        "SR": ["SR", "スーパーレア"],
        "R": [" R ", "レア"],
        "U": [" U ", "アンコモン"],
        "C": [" C ", "コモン"],
        "ALT": ["パラレル", "parallel", "alt"],
    },
    snkrdunk_brand_id="digimoncard",
)

VANGUARD_CONFIG = TCGGameConfig(
    game=TCGGame.VANGUARD,
    display_name_en="Cardfight!! Vanguard",
    display_name_jp="カードファイト!! ヴァンガード",
    keywords_jp={
        "ヴァンガード", "vanguard", "cfv",
        "ブラスター", "ブレード",
    },
    keywords_en={
        "vanguard", "cfv", "cardfight",
        "blaster blade",
    },
    character_keywords={
        "ブラスターブレード", "ドラゴニック",
    },
    set_code_patterns=[
        r'([Dd]\d{3})',  # D001
        r'([Vv]-[A-Z]{2}\d{2})',  # V-BT01
    ],
    card_number_patterns=[
        r'-(\d{3})$',
    ],
    rarity_keywords={
        "VR": ["VR", "ヴァンガードレア"],
        "RRR": ["RRR", "トリプルレア"],
        "RR": ["RR", "ダブルレア"],
        "R": [" R ", "レア"],
        "C": [" C ", "コモン"],
        "SP": ["SP", "スペシャル"],
    },
    snkrdunk_brand_id="vanguard",
)

UNION_ARENA_CONFIG = TCGGameConfig(
    game=TCGGame.UNION_ARENA,
    display_name_en="Union Arena",
    display_name_jp="ユニオンアリーナ",
    keywords_jp={
        "ユニオンアリーナ", "ユニアリ", "union arena",
    },
    keywords_en={
        "union arena", "ua",
    },
    character_keywords=set(),  # Various anime franchises
    set_code_patterns=[
        r'([Uu][Aa]\d{2})',  # UA01
    ],
    card_number_patterns=[
        r'-(\d{3})$',
    ],
    rarity_keywords={
        "SR": ["SR", "スーパーレア"],
        "R": [" R ", "レア"],
        "U": [" U ", "アンコモン"],
        "C": [" C ", "コモン"],
    },
    snkrdunk_brand_id="union-arena",
)

DUEL_MASTERS_CONFIG = TCGGameConfig(
    game=TCGGame.DUEL_MASTERS,
    display_name_en="Duel Masters",
    display_name_jp="デュエルマスターズ",
    keywords_jp={
        "デュエマ", "デュエルマスターズ", "duel masters",
        "ボルシャック", "ドラゴン",
    },
    keywords_en={
        "duel masters", "dm",
        "bolshack",
    },
    character_keywords={
        "ボルシャック・ドラゴン",
    },
    set_code_patterns=[
        r'([Dd][Mm]\d{2})',  # DM01
        r'([Dd][Mm][Rr][Pp]-\d{2})',  # DMRP-01
    ],
    card_number_patterns=[
        r'/(\d{1,3})$',  # /100
        r'-(\d{3})$',
    ],
    rarity_keywords={
        "SR": ["SR", "スーパーレア"],
        "VR": ["VR", "ベリーレア"],
        "R": [" R ", "レア"],
        "U": [" U ", "アンコモン"],
        "C": [" C ", "コモン"],
        "LEGEND": ["LEG", "レジェンド"],
    },
    snkrdunk_brand_id="duelmasters",
)


# ============================================================================
# ALL GAME CONFIGS (for easy iteration)
# ============================================================================

ALL_GAME_CONFIGS: Dict[TCGGame, TCGGameConfig] = {
    TCGGame.POKEMON: POKEMON_CONFIG,
    TCGGame.YUGIOH: YUGIOH_CONFIG,
    TCGGame.ONE_PIECE: ONE_PIECE_CONFIG,
    TCGGame.MAGIC: MAGIC_CONFIG,
    TCGGame.WEISS_SCHWARZ: WEISS_SCHWARZ_CONFIG,
    TCGGame.DRAGON_BALL: DRAGON_BALL_CONFIG,
    TCGGame.DIGIMON: DIGIMON_CONFIG,
    TCGGame.VANGUARD: VANGUARD_CONFIG,
    TCGGame.UNION_ARENA: UNION_ARENA_CONFIG,
    TCGGame.DUEL_MASTERS: DUEL_MASTERS_CONFIG,
}


# ============================================================================
# TCG GAME DETECTOR
# ============================================================================

class TCGGameDetector:
    """
    Detects TCG game type from listing titles and extracts card information.

    This class provides methods to:
    1. Detect which TCG game a listing belongs to
    2. Extract card-specific information (set code, card number, rarity)
    3. Access game configuration for display purposes

    Example:
        detector = TCGGameDetector()

        # Detect game from Japanese title
        game = detector.detect_game("ポケモンカード ピカチュウex SAR [SV2a 165/165]")
        # Returns: TCGGame.POKEMON

        # Detect game from English title
        game = detector.detect_game("Pokemon TCG Charizard ex SAR 151")
        # Returns: TCGGame.POKEMON

        # Extract card info
        info = detector.extract_card_info(title, TCGGame.POKEMON)
        # Returns: {"set_code": "SV2A", "card_number": "165", "rarity": "SAR"}
    """

    def __init__(self):
        """Initialize the detector with compiled regex patterns for performance."""
        self._compiled_patterns: Dict[TCGGame, Dict[str, List[Pattern]]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for all games."""
        for game, config in ALL_GAME_CONFIGS.items():
            self._compiled_patterns[game] = {
                "set_code": [re.compile(p, re.IGNORECASE) for p in config.set_code_patterns],
                "card_number": [re.compile(p, re.IGNORECASE) for p in config.card_number_patterns],
            }

    def detect_game(self, title: str) -> TCGGame:
        """
        Detect TCG game from listing title.

        Uses a scoring system to handle titles that might match multiple games.
        Higher scores indicate stronger matches.

        Args:
            title: Product title (Japanese or English)

        Returns:
            Detected TCGGame enum value, or TCGGame.UNKNOWN if not detected
        """
        if not title:
            return TCGGame.UNKNOWN

        title_lower = title.lower()
        scores: Dict[TCGGame, int] = {}

        for game, config in ALL_GAME_CONFIGS.items():
            score = 0

            # Check Japanese keywords (higher weight)
            for keyword in config.keywords_jp:
                if keyword.lower() in title_lower:
                    score += 3

            # Check English keywords
            for keyword in config.keywords_en:
                if keyword in title_lower:
                    score += 2

            # Check character-specific keywords (bonus)
            for keyword in config.character_keywords:
                if keyword.lower() in title_lower:
                    score += 1

            # Check set code patterns (strong indicator)
            for pattern in self._compiled_patterns[game]["set_code"]:
                if pattern.search(title):
                    score += 4
                    break

            if score > 0:
                scores[game] = score

        if not scores:
            return TCGGame.UNKNOWN

        # Return game with highest score
        return max(scores, key=scores.get)

    def extract_card_info(
        self,
        title: str,
        game: Optional[TCGGame] = None
    ) -> Dict[str, Union[str, bool, float, None]]:
        """
        Extract card information from listing title, including grading info.

        Args:
            title: Product title
            game: TCGGame to use for pattern matching (auto-detects if None)

        Returns:
            Dictionary with extracted card info:
            - game: TCGGame value (str or None)
            - set_code: Set/expansion code (str or None)
            - card_number: Card number within set (str or None)
            - rarity: Card rarity (str or None)
            - language: Card language (defaults to "JP")
            - is_graded: Whether card is professionally graded (bool)
            - grading_company: Grading company name (str or None)
            - grade: Numeric grade value (float or None)
            - grade_qualifier: Grade qualifier like "OC" (str or None)
            - cert_number: Certification number (str or None)
        """
        result: Dict[str, Union[str, bool, float, None]] = {
            "game": None,
            "set_code": None,
            "card_number": None,
            "rarity": None,
            "language": "JP",
            # Grading fields
            "is_graded": False,
            "grading_company": None,
            "grade": None,
            "grade_qualifier": None,
            "cert_number": None,
        }

        if not title:
            return result

        # Auto-detect game if not provided
        detected_game = game or self.detect_game(title)
        result["game"] = detected_game.value if detected_game != TCGGame.UNKNOWN else None

        # Extract grading information (works even if game is unknown)
        grading_info = get_grading_detector().detect_grading(title)
        result["is_graded"] = grading_info.is_graded
        if grading_info.company:
            result["grading_company"] = grading_info.company.value
        result["grade"] = grading_info.grade
        result["grade_qualifier"] = grading_info.grade_qualifier
        result["cert_number"] = grading_info.cert_number

        if detected_game == TCGGame.UNKNOWN:
            return result

        config = ALL_GAME_CONFIGS.get(detected_game)
        if not config:
            return result

        # Extract set code
        for pattern in self._compiled_patterns[detected_game]["set_code"]:
            match = pattern.search(title)
            if match:
                result["set_code"] = match.group(1).upper()
                break

        # Extract card number
        for pattern in self._compiled_patterns[detected_game]["card_number"]:
            match = pattern.search(title)
            if match:
                # Some patterns have multiple groups, get the number group
                groups = match.groups()
                for group in reversed(groups):  # Prefer later groups (usually the number)
                    if group and group.isdigit():
                        result["card_number"] = group.zfill(3)  # Pad to 3 digits
                        break
                if result["card_number"]:
                    break

        # Extract rarity
        title_lower = title.lower()
        for rarity_code, keywords in config.rarity_keywords.items():
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    result["rarity"] = rarity_code
                    break
            if result["rarity"]:
                break

        # Detect language
        if any(kw in title_lower for kw in ["english", "英語", "en版", "海外版"]):
            result["language"] = "EN"
        elif any(kw in title_lower for kw in ["korean", "韓国", "kr版"]):
            result["language"] = "KR"
        elif any(kw in title_lower for kw in ["chinese", "中国", "cn版"]):
            result["language"] = "CN"

        return result

    def get_game_config(self, game: TCGGame) -> Optional[TCGGameConfig]:
        """
        Get configuration for a specific game.

        Args:
            game: TCGGame enum value

        Returns:
            TCGGameConfig or None if game not found
        """
        return ALL_GAME_CONFIGS.get(game)

    def get_all_games(self) -> List[TCGGame]:
        """
        Get list of all supported games.

        Returns:
            List of TCGGame enum values (excluding UNKNOWN)
        """
        return [g for g in TCGGame if g != TCGGame.UNKNOWN]

    def get_snkrdunk_brand_id(self, game: TCGGame) -> Optional[str]:
        """
        Get SNKRDUNK brand ID for a game.

        Args:
            game: TCGGame enum value

        Returns:
            Brand ID string or None if not available on SNKRDUNK
        """
        config = self.get_game_config(game)
        return config.snkrdunk_brand_id if config else None


# ============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ============================================================================

# Singleton detector instance
_detector: Optional[TCGGameDetector] = None


def get_detector() -> TCGGameDetector:
    """Get or create singleton TCGGameDetector instance."""
    global _detector
    if _detector is None:
        _detector = TCGGameDetector()
    return _detector


def detect_tcg_game(title: str) -> TCGGame:
    """
    Convenience function to detect TCG game from title.

    Args:
        title: Product title

    Returns:
        TCGGame enum value
    """
    return get_detector().detect_game(title)


def extract_tcg_card_info(
    title: str,
    game: Optional[TCGGame] = None
) -> Dict[str, Union[str, bool, float, None]]:
    """
    Convenience function to extract card info from title, including grading info.

    Args:
        title: Product title
        game: Optional TCGGame (auto-detects if None)

    Returns:
        Dictionary with card info including:
        - game: TCGGame value (str or None)
        - set_code: Set/expansion code (str or None)
        - card_number: Card number within set (str or None)
        - rarity: Card rarity (str or None)
        - language: Card language (defaults to "JP")
        - is_graded: Whether card is professionally graded (bool)
        - grading_company: Grading company name (str or None)
        - grade: Numeric grade value (float or None)
        - grade_qualifier: Grade qualifier like "OC" (str or None)
        - cert_number: Certification number (str or None)
    """
    return get_detector().extract_card_info(title, game)


def extract_grading_info(title: str) -> GradingInfo:
    """
    Convenience function to extract only grading information from title.

    Args:
        title: Product title

    Returns:
        GradingInfo dataclass with:
        - is_graded: Whether card is professionally graded
        - company: GradingCompany enum (or None)
        - grade: Numeric grade value (or None)
        - grade_qualifier: Grade qualifier (or None)
        - cert_number: Certification number (or None)
    """
    return get_grading_detector().detect_grading(title)


def is_graded_card(title: str) -> bool:
    """
    Quick check if a title indicates a graded card.

    Args:
        title: Product title

    Returns:
        True if the card appears to be professionally graded
    """
    return get_grading_detector().detect_grading(title).is_graded
