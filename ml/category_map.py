"""Map the 10 OPP-115 categories onto the six score categories (plus 'informational')."""

OPP115_TO_SCORE_CATEGORY: dict[str, str] = {
    "First Party Collection/Use": "collection",
    "Third Party Sharing/Collection": "sharing",
    "User Access, Edit and Deletion": "rights",
    "User Choice/Control": "rights",
    "Data Retention": "retention",
    "Data Security": "security",
    "Policy Change": "informational",
    "Do Not Track": "informational",
    "International and Specific Audiences": "informational",
    "Other": "informational",
}

SCORE_CATEGORIES = ["collection", "sharing", "rights", "retention", "security", "informational"]
