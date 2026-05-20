from graph.causal_taxonomy import CAUSAL_TYPES, RELATION_ALIASES, canonicalize_relation


def test_known_causal_types_return_themselves():
    for relation_type, meta in CAUSAL_TYPES.items():
        result = canonicalize_relation(relation_type)
        assert result["canonical"] == relation_type
        assert result["polarity"] == meta["polarity"]
        assert result["strength"] == meta["strength"]
        assert result["is_causal"] == meta["is_causal"]


def test_aliases_map_to_canonical_relations():
    for alias, canonical in RELATION_ALIASES.items():
        assert canonicalize_relation(alias)["canonical"] == canonical


def test_substring_alias_matching():
    assert canonicalize_relation("materially reduce emissions")["canonical"] == "reduces"
    assert canonicalize_relation("can lead to rating uplift")["canonical"] == "leads_to"


def test_unknown_relation_falls_back_to_related_to():
    result = canonicalize_relation("has_document")
    assert result == {
        "canonical": "related_to",
        "polarity": 0,
        "strength": "weak",
        "is_causal": False,
    }
