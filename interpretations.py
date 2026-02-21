"""
Vedic Astrology House Interpretation Engine
============================================

This module provides comprehensive house-by-house interpretations based on classical
Vedic astrology texts including BPHS (Brihat Parashara Hora Shastra), Phalita Jyotisha,
and Saravali. The engine analyzes the placement of planetary lords in various houses and
generates detailed predictions for each of the 12 houses.

The interpretation model follows the ancient principles of:
- Kendra (1,4,7,10): Angular houses representing action and manifestation
- Trikona (5,9): Triangular houses representing dharma and fortune
- Dusthana (6,8,12): Difficult houses representing challenges and transformation
- Upachaya (3,6,10,11): Houses of growth representing improvement over time

Author: Vedic Astrology Engine
Date: 2026
"""

# =============================================================================
# DATA STRUCTURES - RASHI (ZODIAC SIGN) INFORMATION
# =============================================================================

RASHI_INFO = [
    {"name": "Aries", "sanskrit": "Mesha", "lord": "Mars"},
    {"name": "Taurus", "sanskrit": "Vrishabha", "lord": "Venus"},
    {"name": "Gemini", "sanskrit": "Mithuna", "lord": "Mercury"},
    {"name": "Cancer", "sanskrit": "Karka", "lord": "Moon"},
    {"name": "Leo", "sanskrit": "Simha", "lord": "Sun"},
    {"name": "Virgo", "sanskrit": "Kanya", "lord": "Mercury"},
    {"name": "Libra", "sanskrit": "Tula", "lord": "Venus"},
    {"name": "Scorpio", "sanskrit": "Vrischika", "lord": "Mars"},
    {"name": "Sagittarius", "sanskrit": "Dhanu", "lord": "Jupiter"},
    {"name": "Capricorn", "sanskrit": "Makara", "lord": "Saturn"},
    {"name": "Aquarius", "sanskrit": "Kumbha", "lord": "Saturn"},
    {"name": "Pisces", "sanskrit": "Meena", "lord": "Jupiter"},
]

# =============================================================================
# DATA STRUCTURES - HOUSE TITLES AND SIGNIFICATIONS
# =============================================================================

HOUSE_TITLES = {
    1: "1st House — Lagna (Self & Body)",
    2: "2nd House — Dhana (Wealth & Family)",
    3: "3rd House — Parakrama (Courage & Siblings)",
    4: "4th House — Sukha (Home & Happiness)",
    5: "5th House — Putra (Intelligence & Children)",
    6: "6th House — Ripu (Enemies & Health)",
    7: "7th House — Kalatra (Marriage & Partnerships)",
    8: "8th House — Ayur (Longevity & Transformation)",
    9: "9th House — Dharma (Luck & Spirituality)",
    10: "10th House — Karma (Career & Status)",
    11: "11th House — Labha (Gains & Desires)",
    12: "12th House — Vyaya (Losses & Liberation)"
}

HOUSE_SIGNIFICATIONS = {
    1: "The 1st house governs the self, physical body, personality, appearance, health, and overall life direction. It represents the native's vitality, character, and the lens through which they engage with the world.",
    2: "The 2nd house governs wealth, accumulated assets, family of origin, speech, food habits, right eye, and face. It indicates the native's financial standing and relationship with their immediate family.",
    3: "The 3rd house governs courage, initiative, siblings (especially younger), communication, short journeys, writing, and the right ear. It represents mental strength and one's ability to take bold action.",
    4: "The 4th house governs the mother, home, domestic happiness, education, property, vehicles, inner peace, and the heart. It indicates one's foundational emotional security and connection to roots.",
    5: "The 5th house governs intelligence, creativity, children, romance, past-life merits (Poorvapunya), mantras, and speculation. It represents the native's creative power and their connection to future generations.",
    6: "The 6th house governs enemies, diseases, debts, obstacles, service, competition, and daily routines. It indicates the native's ability to overcome adversity and their relationship with health and work.",
    7: "The 7th house governs marriage, life partnerships, business partnerships, legal contracts, open enemies, and travels abroad. It reveals the nature of significant relationships and how one engages with others.",
    8: "The 8th house governs longevity, transformation, hidden knowledge, inheritance, occult sciences, sudden events, and research. It represents the mysteries of life, death, and regeneration.",
    9: "The 9th house governs luck, dharma (righteousness), the father, teachers, higher education, long journeys, spirituality, and divine grace. It is the most auspicious house and indicates one's fortune and spiritual path.",
    10: "The 10th house governs career, profession, status, authority, government, public reputation, and actions in the world. It is the most powerful Kendra and reveals the native's role in society.",
    11: "The 11th house governs income, gains, elder siblings, friends, social networks, fulfillment of desires, and aspirations. It indicates the ease with which one achieves their goals.",
    12: "The 12th house governs losses, expenditure, foreign lands, isolation, spirituality, liberation (Moksha), sleep, hospitals, and retreat. It represents the dissolving of ego boundaries and connection to the infinite."
}

# =============================================================================
# DATA STRUCTURES - PLANET INTERPRETATIONS BY HOUSE
# =============================================================================

PLANET_IN_HOUSE = {
    "Sun": {
        1: "The Sun in the Lagna bestows a confident, authoritative, and self-assured personality. The native is energetic, proud, and naturally inclined toward leadership. Physical vitality is generally good, though there may be a tendency toward egoism. This is a powerful placement that gives prominence and recognition in life.",
        2: "The Sun in the 2nd house indicates wealth through government service or positions of authority. The native tends to speak with authority but may be harsh or domineering in family matters. There can be conflict with the father regarding family wealth. The right eye may need attention.",
        3: "The Sun in the 3rd house makes the native courageous, energetic, and self-motivated. Siblings may be few or the native may be at odds with them. Communication is confident and authoritative. The native has strong willpower and excels in competitive environments.",
        4: "The Sun in the 4th house can indicate challenges in domestic happiness, as the Sun's heat disturbs the peace of this house. The mother may be a strong, authoritative figure. Despite home challenges, the native often achieves good career success and public recognition.",
        5: "The Sun in the 5th house bestows intelligence, leadership ability, and creative power. The native is authoritative with children and may have fewer children but of noble character. This is a good placement for politics, speculation, and creative fields. Past-life merits are strong.",
        6: "The Sun in the 6th house gives victory over enemies and good resistance to disease. The native can excel in competitive fields, government service, and law. This placement strengthens the ability to overcome obstacles through authority and willpower.",
        7: "The Sun in the 7th house can create challenges in marriage, as the native's strong ego may clash with the partner's individuality. The spouse may be from a prominent family. Business partnerships with government authorities can be favorable.",
        8: "The Sun in the 8th house can indicate chronic health issues, particularly related to the heart or eyes. There may be obstacles from authority figures. However, this placement can also give interest in occult sciences and hidden knowledge. Longevity may be affected.",
        9: "The Sun in the 9th house is an excellent placement, making the native fortunate, religious, and ethically inclined. The father is respected and influential. The native receives divine grace and succeeds in higher education, law, and spiritual pursuits.",
        10: "The Sun in the 10th house (digbala) is one of the finest placements for career. The native achieves great authority, fame, and recognition. Success in government, politics, administration, and public life is strongly indicated. This is the sign of a born leader.",
        11: "The Sun in the 11th house brings income through government, authority figures, or the native's own leadership. Social connections are with influential people. Elder siblings may be prominent. Gains are steady and aspirations tend to be fulfilled.",
        12: "The Sun in the 12th house can indicate expenditure of energy in foreign lands or on matters of isolation. The native may face challenges with the government or authority. However, there is a deep spiritual inclination, and the native may find fulfillment through charitable or spiritual work."
    },
    "Moon": {
        1: "The Moon in the Lagna makes the native emotionally sensitive, imaginative, and adaptable. The face is often attractive with a pleasant demeanor. The native is empathetic and deeply connected to their emotional experience. The mind is active and the personality changes with circumstances.",
        2: "The Moon in the 2nd house bestows a pleasant, poetic voice and speech that attracts others. The native enjoys fine food and a comfortable family life. Wealth tends to fluctuate like the Moon's phases. There is a strong emotional bond with the family and a tendency toward generosity.",
        3: "The Moon in the 3rd house creates a restless, curious mind with a talent for communication. The native is brave in an intuitive way and has good relationships with siblings. Short journeys, writing, and artistic communication are favored. The mind is quick and adaptable.",
        4: "The Moon in the 4th house (its own sign position concept) is an excellent placement. The native enjoys a happy domestic life, close relationship with the mother, and emotional contentment. Property ownership is favored. The native finds deep peace in their home environment.",
        5: "The Moon in the 5th house gives a rich emotional intelligence and a natural affinity for children. The native is romantic, artistic, and deeply creative. There is a strong intuitive intelligence and a tendency toward emotional decision-making. Children bring great joy.",
        6: "The Moon in the 6th house can indicate health issues related to digestion, stomach, or the mind. The native may have many adversaries but is emotionally resilient. Service to others comes naturally. Women may play a challenging role in health matters.",
        7: "The Moon in the 7th house gives a charming, gentle, and emotionally open partner. The native seeks emotional security through relationships and is strongly drawn to partnerships. Multiple relationships are possible. Business partnerships with women may be favored.",
        8: "The Moon in the 8th house bestows psychic sensitivity and emotional depth. The native experiences significant emotional transformations throughout life. There may be mother-related challenges. Interest in occult sciences, healing, and hidden knowledge is strong.",
        9: "The Moon in the 9th house makes the native spiritually sensitive, intuitive, and naturally religious. The mother may be deeply spiritual. The native receives divine grace through their emotional openness. Long journeys, particularly pilgrimages, bring fulfillment.",
        10: "The Moon in the 10th house can bring fluctuations in career but gives great public popularity. The native is emotionally invested in their work and often works with the public. Careers in hospitality, healthcare, public service, and creative fields are favored.",
        11: "The Moon in the 11th house brings emotional fulfillment through social connections and a wide network of friends, especially women. Income fluctuates but is generally good. The native's desires are often fulfilled through emotional intelligence and social connections.",
        12: "The Moon in the 12th house gives a rich inner life, strong imagination, and a natural inclination toward spirituality and introspection. The native may sleep well but also tend toward escapism. Foreign connections through women are possible. There is a natural draw toward retreat and meditation."
    },
    "Mars": {
        1: "Mars in the Lagna makes the native energetic, assertive, courageous, and competitive. The physique is typically athletic and the nature is impulsive and action-oriented. There is great ambition and the native does not shy away from confrontation. Accident-proneness is a caution.",
        2: "Mars in the 2nd house indicates wealth earned through significant effort and competition. Speech can be blunt, harsh, or argumentative. There may be conflicts within the family over finances. The native is determined to build material security but may spend aggressively as well.",
        3: "Mars in the 3rd house gives exceptional courage, initiative, and competitive spirit. The native is a natural warrior who leads by example. Siblings may be competitive or there may be conflicts with them. Excellence in sports, military, and any field requiring physical skill is indicated.",
        4: "Mars in the 4th house can disturb domestic peace and create conflicts in the home environment. The mother may be energetic but the relationship can be tense. Property disputes are possible. The native is restless at home and prefers active engagement over domestic life.",
        5: "Mars in the 5th house gives sharp intelligence, a competitive mind, and creative boldness. The native may have fewer children or the first pregnancy may require care. Speculation and risk-taking are common. The native excels in strategic fields, sports, and creative competition.",
        6: "Mars in the 6th house (one of its best positions) gives the native exceptional ability to overcome enemies, disease, and debts. The native is a fierce competitor who triumphs through energy and determination. Success in medicine, law, military, and competitive sports is strongly indicated.",
        7: "Mars in the 7th house (Manglik placement) can create a powerful, energetic spouse who is independent and assertive. Marital conflicts are possible unless the spouse has equivalent energy. Business partnerships benefit from Mars's drive. The native is passionate and direct in relationships.",
        8: "Mars in the 8th house can indicate accidents, surgeries, or sudden events. The native has research abilities and an interest in occult and hidden sciences. Longevity may be affected, though the native has a fighting spirit. This placement can give great courage in facing life's challenges.",
        9: "Mars in the 9th house creates an independent and assertive approach to spirituality and dharma. The native may disagree with conventional religious views. The father or guru relationship may involve conflict. Long journeys are taken with great courage and initiative.",
        10: "Mars in the 10th house is an excellent career placement. The native achieves authority and recognition through bold action, competition, and leadership. Careers in engineering, military, police, sports, surgery, and any demanding field are favored. Ambition drives great achievement.",
        11: "Mars in the 11th house gives strong income through competitive efforts. The native's friends are energetic, competitive, and driven. Elder siblings are assertive. Gains come through enterprise and determination. Social networks tend to be action-oriented.",
        12: "Mars in the 12th house can indicate expenditure on property, hidden enemies, or stay in foreign lands. The native may experience anger-related self-sabotage. However, this placement can also give energy for spiritual practice, charitable work, and healing arts."
    },
    "Mercury": {
        1: "Mercury in the Lagna bestows intelligence, wit, communication skills, and a youthful appearance that persists through life. The native is naturally curious, analytical, and loves to learn and share knowledge. Business acumen and quick thinking are characteristic strengths.",
        2: "Mercury in the 2nd house gives eloquence, business intelligence, and the ability to earn through communication, writing, or trade. The native may speak multiple languages. Financial intelligence is high and wealth comes through intellectual or mercantile pursuits.",
        3: "Mercury in the 3rd house is an excellent placement, giving skillful writing, speaking, and communication. The native excels in media, journalism, teaching, and any field requiring intellectual expression. Relationships with siblings are intellectually stimulating.",
        4: "Mercury in the 4th house gives a good, analytical mind shaped by strong education. The native loves learning and may be a lifelong student. The home may serve as a place of study or intellectual activity. The mother is likely educated and intellectually inclined.",
        5: "Mercury in the 5th house is a powerful placement for intelligence, giving extraordinary analytical and creative capacity. The native may excel in teaching, writing, mathematics, or any intellectually creative field. Children tend to be intelligent and communicative.",
        6: "Mercury in the 6th house gives the native the ability to overcome obstacles through analytical thinking and communication. Success in service industries, healthcare administration, law, and accounting is indicated. Health issues related to the nervous system may need attention.",
        7: "Mercury in the 7th house indicates an intelligent, communicative, and business-minded partner. The native is attracted to mentally stimulating relationships. Business partnerships formed through communication and intellect tend to prosper. Legal matters are handled skillfully.",
        8: "Mercury in the 8th house gives exceptional research abilities, an interest in hidden subjects, and a penetrating intellect. The native may excel in occult sciences, astrology, psychology, and investigative fields. Written communication about transformation and mysteries is gifted.",
        9: "Mercury in the 9th house gives a philosophical, scholarly mind that excels in higher education, religious scholarship, and long-distance communication. The native may be a teacher, author, or spiritual writer. The father and guru are likely educated and communicative.",
        10: "Mercury in the 10th house is excellent for a career in communication, business, writing, accounting, or any intellectual profession. The native is known for their sharp mind and communicative skills in the professional world. Multiple career pursuits are common.",
        11: "Mercury in the 11th house gives income through intellectual skills, writing, or business. Social circles are with educated, communicative people. Desires tend to be intellectually oriented and are generally fulfilled. Elder siblings may be articulate and business-minded.",
        12: "Mercury in the 12th house gives a rich, analytical inner life and a talent for introspection. The native may be drawn to research in isolated settings or foreign countries. There is a gift for languages and cross-cultural communication. Spiritual and philosophical writing is favored."
    },
    "Jupiter": {
        1: "Jupiter in the Lagna is one of the most auspicious placements. The native is wise, optimistic, generous, and spiritually inclined. Physical health is generally robust and the native has a natural nobility of character. Teaching, counseling, and spiritual guidance come naturally.",
        2: "Jupiter in the 2nd house bestows significant wealth, an eloquent and truthful speech, and a large, happy family. The native is generous with resources and inspires others through wise counsel. Financial abundance grows through ethical means and good fortune.",
        3: "Jupiter in the 3rd house gives a wise, philosophical approach to courage and communication. The native may be a spiritual writer or teacher. Siblings are often wise or educated. The native travels for educational or spiritual purposes and expresses wisdom through writing.",
        4: "Jupiter in the 4th house gives happiness, a devoted mother, excellent education, property, and a spiritually uplifting home environment. The native finds deep contentment in domestic life. This is a placement of material and emotional comfort rooted in wisdom and dharma.",
        5: "Jupiter in the 5th house is exceptionally auspicious, giving brilliant children, great intelligence, and creative power rooted in wisdom. The native may be a teacher, advisor, or spiritual guide. Past-life merits are strong, and divine grace supports all creative endeavors.",
        6: "Jupiter in the 6th house helps the native overcome enemies, debts, and diseases through wisdom and ethical behavior. The native may work in healthcare, law, or social service. While challenges exist, Jupiter's grace ensures ultimate victory over adversity.",
        7: "Jupiter in the 7th house gives an excellent spouse who is wise, educated, and spiritually inclined. Partnerships of all kinds are blessed. The native may meet their spouse through educational or spiritual settings. Business partnerships are ethically conducted and prosperous.",
        8: "Jupiter in the 8th house gives longevity, interest in metaphysical knowledge, and the ability to find meaning in life's deepest transformations. Inheritance is possible. The native has a philosophical approach to death and transformation that brings wisdom through adversity.",
        9: "Jupiter in the 9th house (one of its best placements) makes the native extremely fortunate, deeply religious, and spiritually advanced. The father and guru are revered guides. Higher education brings great success. Divine grace flows abundantly in the native's life.",
        10: "Jupiter in the 10th house gives an excellent, respected career in teaching, law, spirituality, or advisory roles. The native is known for wisdom, integrity, and ethical leadership. Recognition comes through noble deeds and the native often holds positions of significant authority.",
        11: "Jupiter in the 11th house brings abundant gains, a network of wise and influential friends, and the fulfillment of meaningful desires. The native attracts prosperity through their wisdom and generosity. Elder siblings may be respected or scholarly figures.",
        12: "Jupiter in the 12th house inclines the native toward spiritual liberation, retreat, and charitable service. Foreign lands may bring spiritual fulfillment. The native is generous to a fault and finds meaning in giving rather than accumulating. This placement can indicate moksha."
    },
    "Venus": {
        1: "Venus in the Lagna bestows beauty, charm, artistic talent, and a naturally pleasing personality. The native is romantic, sociable, and aesthetically sensitive. Love of luxury, refinement, and the arts shapes the native's approach to life. Relationships come easily and naturally.",
        2: "Venus in the 2nd house gives significant wealth, a beautiful and melodious voice, and a love of fine food and luxuries. Family life is harmonious and artistic. The native earns through beauty-related fields, arts, or luxury goods. Financial comfort is generally assured.",
        3: "Venus in the 3rd house gives artistic communication skills, a charming way with words, and a love of short pleasurable journeys. Siblings may be artistic or of the opposite sex in significant numbers. The native excels in artistic writing, music, and diplomatic communication.",
        4: "Venus in the 4th house gives a beautiful, comfortable home environment and a loving, nurturing mother. The native finds deep happiness in domestic life and appreciates beauty in their surroundings. Property, vehicles, and worldly comforts are favored by this placement.",
        5: "Venus in the 5th house gives artistic creativity, romantic inclinations, and children who are beautiful or artistically gifted. The native excels in performing arts, creative industries, and romantic pursuits. Love affairs may be numerous and the capacity for artistic expression is exceptional.",
        6: "Venus in the 6th house helps overcome enemies through charm and diplomacy. The native may work in healthcare aesthetics, luxury service industries, or diplomatic roles. Health challenges related to the reproductive system or kidneys may need attention.",
        7: "Venus in the 7th house is one of the finest placements for marriage, giving a beautiful, charming, and loving spouse. Partnerships of all kinds are harmonious and mutually beneficial. The native has natural charisma in one-on-one relationships and business partnerships flourish.",
        8: "Venus in the 8th house gives sensual depth, an interest in hidden or taboo pleasures, and possible inheritance through the partner or spouse. The native has an instinctive understanding of transformation and often finds beauty in life's mysteries. Longevity is generally indicated.",
        9: "Venus in the 9th house gives a harmonious and fortunate life, with a love of spiritual beauty, religious arts, and philosophical aesthetics. The native may be involved in spiritual music, sacred arts, or devotional practices. Long journeys bring romantic or artistic fulfillment.",
        10: "Venus in the 10th house gives a career in the arts, beauty, fashion, luxury, hospitality, or entertainment. The native achieves fame through their aesthetic sensibility and charm. Public recognition comes through artistic or diplomatic achievements.",
        11: "Venus in the 11th house brings income through artistic or luxury fields and attracts a beautiful, harmonious social circle. Desires related to love, beauty, and comfort are fulfilled. Elder siblings may be artistic or of significant help in achieving aspirations.",
        12: "Venus in the 12th house gives a love of privacy, spiritual devotion, and pleasures found in retreat or foreign lands. The native may form relationships in private or foreign settings. There is artistic or spiritual fulfillment through isolation, meditation, or service."
    },
    "Saturn": {
        1: "Saturn in the Lagna makes the native serious, disciplined, hardworking, and persevering. The appearance may be dark or lean and the native may have a reserved, cautious demeanor. Life lessons come through discipline and responsibility. Success comes slowly but surely through sustained effort.",
        2: "Saturn in the 2nd house creates delays or obstacles in wealth accumulation and may indicate separation from family or speech that is measured and serious. Wealth eventually comes through disciplined savings and hard work, though financial abundance may arrive later in life.",
        3: "Saturn in the 3rd house gives exceptional discipline and endurance in all undertakings. The native is a persistent, methodical communicator. Relationships with siblings may be distant or involve responsibilities. The native succeeds in any field requiring sustained effort and discipline.",
        4: "Saturn in the 4th house can indicate a challenging relationship with the mother or a difficult early home environment. Domestic happiness may be delayed. However, the native often acquires property and establishes a stable home through sustained effort in later years.",
        5: "Saturn in the 5th house may indicate delays in having children or a small number of children. The native is a serious, methodical thinker who excels in structured intellectual pursuits. Creative expression tends toward classical or disciplined forms rather than spontaneous creativity.",
        6: "Saturn in the 6th house is a powerful placement for overcoming enemies, chronic diseases, and debts through sheer persistence and discipline. The native thrives in service-oriented careers that require stamina. This is considered one of Saturn's best positions for worldly success.",
        7: "Saturn in the 7th house may delay marriage or bring an older, more serious partner. Partnerships are approached with caution and practicality. Once established, relationships are stable and long-lasting. Business partnerships are built on discipline and mutual responsibility.",
        8: "Saturn in the 8th house gives longevity through disciplined health practices. The native may experience chronic health challenges but has remarkable endurance. Research, occult sciences, and understanding of the deeper mechanisms of life attract this placement's energy.",
        9: "Saturn in the 9th house creates a serious, responsible approach to spirituality and dharma. The native may follow traditional religious practices with discipline. The relationship with the father or guru involves karmic lessons. Fortune comes through perseverance and ethical living.",
        10: "Saturn in the 10th house (its digbala) is one of its strongest placements, giving a distinguished career through sustained effort, discipline, and responsibility. The native rises to senior positions through merit and hard work. Careers in government, administration, law, and engineering are favored.",
        11: "Saturn in the 11th house gives steady, dependable income that grows through disciplined effort. Social circles tend to be older or more traditional. Elder siblings may bring responsibilities. Aspirations are achieved through patience and persistent action.",
        12: "Saturn in the 12th house inclines the native toward spiritual discipline, monastic tendencies, and work in isolated or institutional settings. Foreign assignments or service in charitable institutions are possible. This placement is favorable for spiritual liberation through disciplined practice."
    },
    "Rahu": {
        1: "Rahu in the Lagna gives an unusual, magnetic personality with strong worldly ambitions. The native is unconventional, innovative, and driven to make an impact. Foreign cultures, technology, and new ideas attract this placement. There may be obsession with the self and its presentation to the world.",
        2: "Rahu in the 2nd house creates unusual or unconventional pathways to wealth. The native may earn through foreign connections, technology, or unusual means. Speech can be persuasive but not always truthful. Family connections may be complex or involve foreign elements.",
        3: "Rahu in the 3rd house gives an unconventional, bold approach to communication and courage. The native may be drawn to cutting-edge media, digital communication, or foreign languages. Initiative is strong and the native is willing to take unusual risks in pursuit of goals.",
        4: "Rahu in the 4th house creates an unusual domestic environment, possibly involving foreign cultures or technology in the home. The mother may be unconventional. Property may be acquired through unusual means. Inner peace is sought through achievement and material comfort.",
        5: "Rahu in the 5th house gives unconventional intelligence, unusual or adopted children, and a creative approach that breaks conventional boundaries. Speculation and risk-taking are attractive. The native may be drawn to unusual or foreign forms of creative expression.",
        6: "Rahu in the 6th house gives a powerful, unconventional ability to defeat enemies and overcome disease. The native may use unusual methods in service or healthcare. Foreign or technological approaches to solving problems are favored. Competition is handled with strategic cunning.",
        7: "Rahu in the 7th house may bring a foreign or unconventional partner, or indicate that the native seeks relationships that are outside their cultural norm. Business partnerships with foreigners or in technology fields are favored. Multiple or unusual partnerships are possible.",
        8: "Rahu in the 8th house gives deep interest in occult sciences, mystical knowledge, and the hidden aspects of existence. The native may experience sudden transformations. Research in unusual or taboo subjects is attractive. Foreign inheritances or sudden windfalls are possible.",
        9: "Rahu in the 9th house creates an unconventional approach to spirituality and dharma. The native may follow non-traditional spiritual paths or a foreign guru. Higher education may be in unconventional fields. Fortune comes through bold, innovative approaches.",
        10: "Rahu in the 10th house gives strong ambition and the drive to achieve recognition through unconventional means. Careers in technology, foreign companies, media, or innovative fields are favored. The native may achieve sudden fame or notoriety. Success in modern, cutting-edge industries is indicated.",
        11: "Rahu in the 11th house gives strong desire for gains and the ability to achieve aspirations through unconventional networks. Income from foreign sources, technology, or unusual industries is possible. Social circles are diverse, international, or connected to innovative fields.",
        12: "Rahu in the 12th house gives an intense pull toward foreign lands, spiritual realms, and the dissolution of boundaries. The native may spend significantly on foreign travel or spiritual pursuits. Unusual spiritual experiences and foreign residency are strongly indicated."
    },
    "Ketu": {
        1: "Ketu in the Lagna gives a spiritually oriented personality that is detached from worldly concerns. The native may be psychic, intuitive, and disconnected from their physical self in some way. Past-life spiritual practices influence the current life. The native often seeks meaning beyond the material world.",
        2: "Ketu in the 2nd house indicates spiritual detachment from wealth and family. The native may speak in unusual ways or about spiritual subjects. Family connections may involve past-life karma. Wealth matters are approached with detachment and there may be unexpected losses or gains.",
        3: "Ketu in the 3rd house gives spiritual courage and an unusual approach to communication. The native may communicate in mysterious or symbolic ways. Relationships with siblings carry past-life significance. Short journeys often have a spiritual or investigative purpose.",
        4: "Ketu in the 4th house creates inner spiritual peace that transcends external domestic circumstances. The native may be detached from home and mother in some way. Property matters carry past-life karma. The native finds true peace within rather than in external circumstances.",
        5: "Ketu in the 5th house gives spiritual intelligence and deep past-life merits that support the current life. Children may have a spiritual or unusual quality. The native is intuitive and may have psychic abilities. Creative expression is spiritually motivated.",
        6: "Ketu in the 6th house gives the native powerful ability to overcome enemies and disease through spiritual means and karma. Service to the underprivileged or spiritually distressed comes naturally. The native may work in healing or investigative fields with intuitive insight.",
        7: "Ketu in the 7th house indicates a spiritually significant partnership or a tendency toward detachment in relationships. The spouse may be spiritual or otherworldly. Past-life karma with partners is being resolved. The native seeks a partner who honors their spiritual nature.",
        8: "Ketu in the 8th house gives exceptional past-life experience with occult sciences and the mysteries of existence. The native has deep, instinctive knowledge of transformation and the cycle of death and rebirth. This placement is very favorable for moksha and spiritual liberation.",
        9: "Ketu in the 9th house gives deep, innate spiritual wisdom from past lives. The native may be naturally philosophical without requiring formal religious training. The relationship with the father or guru carries past-life significance. Fortune comes through spiritual practice.",
        10: "Ketu in the 10th house creates a complex relationship with career and status. The native may be highly skilled in their field but detached from recognition. Career in spirituality, healing, or investigative fields is possible. Past-life professional karma shapes the current path.",
        11: "Ketu in the 11th house gives a spiritual approach to gains and social connections. The native may be detached from material aspirations. Social networks may include spiritual or unusual individuals. Gains come unexpectedly as the native is not focused on accumulation.",
        12: "Ketu in the 12th house (one of its best positions) gives exceptional spiritual depth, a gift for meditation, and strong progress toward moksha. The native may have spent previous lives in monasteries or on spiritual retreat. Liberation through inner exploration is strongly indicated."
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_rashi_info(sign_index):
    """
    Retrieve rashi (zodiac sign) information by index.
    
    Args:
        sign_index (int): Index from 0-11 representing the zodiac sign
        
    Returns:
        dict: Contains 'name', 'sanskrit', and 'lord' keys for the rashi
        
    Raises:
        IndexError: If sign_index is outside 0-11 range
    """
    if not 0 <= sign_index <= 11:
        raise IndexError(f"Sign index must be 0-11, got {sign_index}")
    return RASHI_INFO[sign_index]


def calculate_relative_house_position(house_num, lord_house):
    """
    Calculate the relative position of a house lord from its own house.
    
    According to BPHS, the position of a house lord relative to its own house
    determines the strength and nature of its influence on the house significations.
    
    Formula: relative_position = ((lord_house - house_num) % 12) + 1
    
    This gives a position from 1-12 where:
    - 1 (same house): Self-contained, direct influence
    - 5, 9 (Trikona): Excellent, dharmic support
    - 1, 4, 7, 10 (Kendra): Good, action-oriented support
    - 2, 11 (Financial): Wealth support
    - 3, 6 (Effort): Requires effort, moderate results
    - 8, 12 (Difficult): Challenges, hidden difficulties
    
    Args:
        house_num (int): The house being analyzed (1-12)
        lord_house (int): The house where the lord is placed (1-12)
        
    Returns:
        int: Relative position (1-12)
    """
    return ((lord_house - house_num) % 12) + 1 if house_num != lord_house else 1


def get_house_lord_analysis(house_num, lord_name, lord_house):
    """
    Generate a detailed paragraph analyzing the placement of a house lord.
    
    Based on classical BPHS principles, this function evaluates how a house lord's
    placement affects the significations of its house. The analysis considers:
    
    - Kendra (1,4,7,10): Angular houses providing direct manifestation power
    - Trikona (5,9): Triangular houses providing dharmic and fortuitous support
    - Dusthana (6,8,12): Difficult houses indicating challenges or transformation
    - Upachaya (3,6,10,11): Houses of improvement and growth
    
    Args:
        house_num (int): The house being analyzed (1-12)
        lord_name (str): Name of the planet that rules the house
        lord_house (int): The house where the lord is currently placed (1-12)
        
    Returns:
        str: A detailed 2-3 sentence paragraph analyzing the lord's influence
    """
    
    # Get relative position using BPHS formula
    relative = calculate_relative_house_position(house_num, lord_house)
    
    # Get house significations for context
    analysis_house_sig = HOUSE_SIGNIFICATIONS[lord_house]
    own_house_sig = HOUSE_SIGNIFICATIONS[house_num]
    
    # Determine the strength category and apply appropriate interpretation
    
    if relative == 1:
        # Lord in its own house - self-contained, direct and powerful
        bphs_rule = f"The {lord_name}, as lord of the {house_num}th house, occupies its own house, creating a self-contained and direct manifestation of the house's significations."
        effect = f"This placement ensures that matters of {own_house_sig.split('governs')[1].split('.')[0].strip()} are handled with the planet's own strength and integrity."
        
    elif relative in [5, 9]:
        # Trikona houses - excellent, dharmic support
        trikona_names = {5: "5th (Trikona - intelligence and merit)", 9: "9th (Trikona - luck and dharma)"}
        bphs_rule = f"The {lord_name}, lord of the {house_num}th house, is placed in the {trikona_names[relative]}, which represents exceptional dharmic support according to BPHS principles."
        effect = f"This positioning greatly amplifies the native's ability to manifest the {house_num}th house's significations through righteous action and divine grace."
        
    elif relative in [1, 4, 7, 10]:
        # Kendra houses - angular, action-oriented
        if relative != 1:  # Already handled above
            kendra_names = {4: "4th (Kendra)", 7: "7th (Kendra)", 10: "10th (Kendra)"}
            bphs_rule = f"The {lord_name}, ruling the {house_num}th house, is placed in the {kendra_names[relative]}, an angular house that provides direct manifestation power."
            effect = f"The native experiences strong, visible support for {own_house_sig.split('governs')[1].split('.')[0].strip()} through practical action and engagement."
        else:
            bphs_rule = ""
            effect = ""
    
    elif relative in [2, 11]:
        # Financial houses - wealth and gains
        house_names = {2: "2nd (Dhana - wealth)", 11: "11th (Labha - gains)"}
        bphs_rule = f"The {lord_name}, lord of the {house_num}th house, is placed in the {house_names[relative]}, a house of financial prosperity and gains."
        effect = f"This configuration suggests that the native benefits financially and materially from matters of the {house_num}th house."
        
    elif relative in [3, 6]:
        # Effort houses - moderate results, some challenges
        effort_names = {3: "3rd (courage and effort)", 6: "6th (enemies and challenge)"}
        bphs_rule = f"The {lord_name}, governing the {house_num}th house, is placed in the {effort_names[relative]}, a house requiring sustained effort and perseverance."
        effect = f"Success with the {house_num}th house's significations requires the native's active engagement and determination to overcome obstacles."
        
    elif relative in [8, 12]:
        # Difficult houses - challenges or transformation
        difficult_names = {8: "8th (transformation and mystery)", 12: "12th (loss and liberation)"}
        bphs_rule = f"The {lord_name}, lord of the {house_num}th house, occupies the {difficult_names[relative]}, a house of challenge, transformation, or hidden influence."
        effect = f"The native may experience obstacles or require deeper spiritual understanding to fully utilize the potential of the {house_num}th house."
        
    else:
        bphs_rule = f"The {lord_name}, ruling the {house_num}th house, is placed in the {lord_house}th house."
        effect = f"This placement influences how the native expresses and experiences {own_house_sig.split('governs')[1].split('.')[0].strip()}."
    
    return f"{bphs_rule} {effect}"


def get_planet_analysis(house_num, planets):
    """
    Generate a paragraph analyzing planets occupying a specific house.
    
    If multiple planets occupy the house, describes their combined influence.
    If no planets occupy the house, returns an appropriate statement.
    
    Args:
        house_num (int): The house being analyzed (1-12)
        planets (list): List of planet names occupying this house
        
    Returns:
        str: A 2-3 sentence paragraph describing the planets' influence
    """
    if not planets:
        return f"No planets occupy the {house_num}th house, so the influence is primarily through the house lord."
    
    if len(planets) == 1:
        planet = planets[0]
        house_analysis = PLANET_IN_HOUSE.get(planet, {}).get(house_num, "")
        if house_analysis:
            return house_analysis
        else:
            return f"{planet} in the {house_num}th house brings its characteristic influence to this house's significations."
    
    else:
        # Multiple planets - describe combined influence
        planet_list = ", ".join(planets[:-1]) + f", and {planets[-1]}" if len(planets) > 1 else planets[0]
        return f"Multiple planets including {planet_list} occupy the {house_num}th house, creating a complex interaction of influences. The native experiences a blending of these planetary energies in the affairs of this house, requiring careful synthesis of their individual characteristics."


def get_overall_prediction(house_num, lord_name, lord_house, occupants, 
                          lord_analysis, planet_analysis):
    """
    Generate a comprehensive overall prediction paragraph synthesizing all factors.
    
    This function combines the house lord analysis, planet occupations, and
    relative house positions to create a coherent narrative prediction for
    the native's experience with this house's significations.
    
    Args:
        house_num (int): The house being analyzed (1-12)
        lord_name (str): Name of the house's lord
        lord_house (int): House where the lord is placed
        occupants (list): List of planets in the house
        lord_analysis (str): The paragraph analysis of the lord's placement
        planet_analysis (str): The paragraph analysis of occupants
        
    Returns:
        str: A synthesized prediction paragraph (3-4 sentences)
    """
    relative = calculate_relative_house_position(house_num, lord_house)
    house_sig = HOUSE_SIGNIFICATIONS[house_num].split("governs")[1].split(".")[0].strip()
    
    # Determine overall tone based on house lord position
    if relative in [5, 9]:
        strength = "powerfully supports"
        potential = "exceptional potential"
    elif relative in [1, 4, 7, 10]:
        strength = "actively supports"
        potential = "strong potential"
    elif relative in [2, 11]:
        strength = "materially supports"
        potential = "good potential for gains"
    elif relative in [3, 6]:
        strength = "moderately supports with effort"
        potential = "potential requiring perseverance"
    elif relative in [8, 12]:
        strength = "mystically influences"
        potential = "transformative potential"
    else:
        strength = "influences"
        potential = "potential"
    
    # Build the prediction
    prediction = f"The placement of {lord_name} in the {lord_house}th house {strength} matters of {house_sig}. "
    
    if occupants:
        prediction += f"The presence of {', '.join(occupants)} in the {house_num}th house adds complexity and dimension to these affairs. "
    
    prediction += f"Overall, the native has {potential} in matters of the {house_num}th house, with success dependent on harmonizing the influences of the house lord and any planets occupying this house."
    
    return prediction


# =============================================================================
# MAIN INTERPRETATION FUNCTION
# =============================================================================

def generate_interpretations(chart_data):
    """
    Generate comprehensive house-by-house interpretations for a Vedic astrology chart.
    
    This is the main function that synthesizes all house analysis into a complete
    interpretive framework. It processes the chart data to determine:
    
    1. Which zodiac sign occupies each house (based on ascendant)
    2. Which planet rules each house (the house lord)
    3. Which house the lord is placed in
    4. Which planets occupy each house
    5. Synthesizes all factors into coherent interpretations
    
    The chart_data structure expected:
    {
        "ascendant": {
            "longitude": float,
            "sign_index": int (0-11),
            "rashi": {"name": str, "sanskrit": str, "lord": str}
        },
        "planets": [
            {
                "name": str,
                "house": int (1-12),
                "sign_index": int (0-11),
                "rashi": {"name": str, "sanskrit": str, "lord": str},
                "retrograde": bool,
                "longitude": float
            },
            ...
        ]
    }
    
    Args:
        chart_data (dict): The calculated chart positions from chart_gen.py
        
    Returns:
        list: A list of 12 dicts (one per house), each containing:
            - house (int): House number 1-12
            - sign (str): Zodiac sign name (e.g., "Aries")
            - sign_sanskrit (str): Sanskrit name of the sign (e.g., "Mesha")
            - lord (str): Name of the planet ruling the sign
            - lord_house (int): Which house the lord is placed in
            - occupants (list): Planet names occupying this house
            - title (str): Formatted house title
            - significations (str): Natural significations of the house
            - lord_analysis (str): Analysis of where the lord is placed
            - planet_analysis (str): Analysis of planets in the house
            - overall (str): Synthesized overall prediction
    """
    
    # Extract data from chart_data
    ascendant_sign_index = chart_data["ascendant"]["sign_index"]
    planets_list = chart_data["planets"]
    
    # Build a map of planet positions for quick lookup
    planet_houses = {}  # {planet_name: house_number}
    for planet in planets_list:
        planet_houses[planet["name"]] = planet["house"]
    
    # Build a map of occupants by house
    house_occupants = {i: [] for i in range(1, 13)}
    for planet in planets_list:
        if planet["name"] not in ["Rahu", "Ketu"]:  # Exclude shadow planets from occupants typically, but include per instructions
            house_occupants[planet["house"]].append(planet["name"])
    
    # Actually, let's include all planets as per the spec
    house_occupants = {i: [] for i in range(1, 13)}
    for planet in planets_list:
        house_occupants[planet["house"]].append(planet["name"])
    
    # Generate interpretations for all 12 houses
    interpretations = []
    
    for house_num in range(1, 13):
        # Calculate which sign occupies this house
        # House 1 has the ascendant sign, House 2 is next, etc.
        sign_index = (ascendant_sign_index + house_num - 1) % 12
        rashi_info = get_rashi_info(sign_index)
        
        # Get the house lord
        lord_name = rashi_info["lord"]
        
        # Find which house the lord is placed in
        lord_house = planet_houses.get(lord_name, None)
        if lord_house is None:
            # If lord not found in planets (shouldn't happen with proper data)
            lord_house = house_num
        
        # Get planets occupying this house
        occupants = house_occupants[house_num]
        
        # Generate analyses
        lord_analysis = get_house_lord_analysis(house_num, lord_name, lord_house)
        planet_analysis = get_planet_analysis(house_num, occupants)
        overall = get_overall_prediction(house_num, lord_name, lord_house, occupants,
                                        lord_analysis, planet_analysis)
        
        # Build the interpretation dict for this house
        interpretation = {
            "house": house_num,
            "sign": rashi_info["name"],
            "sign_sanskrit": rashi_info["sanskrit"],
            "lord": lord_name,
            "lord_house": lord_house,
            "occupants": occupants,
            "title": HOUSE_TITLES[house_num],
            "significations": HOUSE_SIGNIFICATIONS[house_num],
            "lord_analysis": lord_analysis,
            "planet_analysis": planet_analysis,
            "overall": overall,
        }
        
        interpretations.append(interpretation)
    
    return interpretations


# =============================================================================
# END OF FILE
# =============================================================================
