import os

import pytest

from textx import metamodel_from_file
from textx.exceptions import TextXSemanticError

current_dir = os.path.join(os.path.dirname(__file__), "namespaced")


def mm_of(relpath):
    return metamodel_from_file(os.path.join(current_dir, relpath))


def test_namespaced_import_resolves_qualified_reference():
    """
    Rules from `import "types.tx" as types` are visible through the
    namespace prefix.
    """
    mm = mm_of("main.tx")

    assert mm["Entity"]._tx_attrs["t"].cls is mm["types.Type"]

    model = mm.model_from_str("entity e1 has type t1")
    assert model.name == "e1"
    assert type(model.t) is mm["types.Type"]
    assert model.t.name == "t1"


def test_namespaced_import_does_not_flatten():
    """
    Names imported with `as` do not occupy rule names of the importing
    grammar.
    """
    mm = mm_of("main.tx")

    # The unqualified name is not visible in the importing grammar.
    with pytest.raises(KeyError):
        mm["Type"]


def test_unprefixed_reference_to_namespaced_rule_fails():
    """
    Unqualified references are resolved only in the current grammar and
    the builtin BASETYPE rules. A rule available only through an aliased
    import is reported with a hint.
    """
    with pytest.raises(TextXSemanticError) as e:
        mm_of("main_unprefixed.tx")

    message = str(e.value)
    assert 'Unknown rule "Type"' in message
    assert 'Use "types.Type"' in message
    assert 'Referenced in rule "Entity"' in message


def test_local_rule_takes_precedence_over_namespaced_import():
    """
    A rule defined in the current grammar shadows same-named rules of
    aliased imports; the imported rule is still reachable via the prefix.
    """
    mm = mm_of("main_local_shadow.tx")

    local_type = mm["Type"]
    imported_type = mm["types.Type"]
    assert local_type is not imported_type
    assert mm["Entity"]._tx_attrs["local"].cls is local_type
    assert mm["Entity"]._tx_attrs["imported"].cls is imported_type

    model = mm.model_from_str("entity localtype x type y")
    assert type(model.local) is local_type
    assert type(model.imported) is imported_type


def test_import_without_alias_keeps_flattening():
    """
    Imports without `as` keep the old behavior: imported rules are
    searched by unqualified references.
    """
    mm = mm_of("flatten.tx")

    assert mm["Entity"]._tx_attrs["t"].cls is mm["types.Type"]


def test_same_rule_name_in_multiple_imports():
    """
    Same-named rules from multiple aliased imports are both usable
    through qualified references.
    """
    mm = mm_of(os.path.join("multi", "main.tx"))

    type_a = mm["types_a.Type"]
    type_b = mm["types_b.Type"]
    assert type_a is not type_b
    assert mm["Entity"]._tx_attrs["x"].cls is type_a
    assert mm["Entity"]._tx_attrs["y"].cls is type_b

    model = mm.model_from_str("entity typea one typeb two")
    assert type(model.x) is type_a
    assert type(model.y) is type_b


def test_ambiguous_unprefixed_reference_lists_candidate_namespaces():
    """
    An unqualified reference to a rule defined in multiple aliased
    imports reports an ambiguity error listing all candidate namespaces.
    """
    with pytest.raises(TextXSemanticError) as e:
        mm_of(os.path.join("multi", "main_ambiguous.tx"))

    message = str(e.value)
    assert 'Ambiguous reference "Type"' in message
    assert "namespaces: a, b" in message
    assert 'Referenced in rule "Entity"' in message


def test_nested_import_chain():
    """
    Nested imports (A imports B, B imports C) are resolved through
    chained prefixes (`b.c.Base`).
    """
    mm = mm_of(os.path.join("nested", "a.tx"))

    assert mm["A"]._tx_attrs["x"].cls is mm["c.Base"]

    model = mm.model_from_str("a base x1")
    assert type(model.x) is mm["c.Base"]
    assert model.x.name == "x1"


def test_diamond_imports_share_classes():
    """
    A grammar imported through multiple aliased paths results in a
    single meta-class.
    """
    mm = mm_of(os.path.join("diamond", "top.tx"))

    base = mm["shared.Base"]
    assert mm["Top"]._tx_attrs["a"].cls is base
    assert mm["Top"]._tx_attrs["b"].cls is base


def test_import_cycle_is_reported_with_cycle_path():
    """
    Import cycles are detected during meta-model construction and the
    error message contains the cycle path.
    """
    with pytest.raises(TextXSemanticError) as e:
        mm_of(os.path.join("cycle", "x.tx"))

    message = str(e.value)
    assert "Import cycle detected" in message
    assert "x -> y -> x" in message
    # The error is reported at the import statement of the grammar
    # that closes the cycle.
    assert e.value.filename.endswith("y.tx")
    assert e.value.line == 1


def test_self_import_cycle():
    with pytest.raises(TextXSemanticError) as e:
        mm_of(os.path.join("cycle", "self.tx"))

    assert "Import cycle detected" in str(e.value)
    assert "self -> self" in str(e.value)


def test_obj_ref_to_namespaced_class():
    """
    Object cross-references may target classes from aliased imports.
    """
    mm = mm_of(os.path.join("objref", "main.tx"))

    model = mm.model_from_str(
        """
        type t1
        entity e1 uses t1
        """
    )
    assert type(model.types[0]) is mm["types.Type"]
    assert model.entities[0].ref is model.types[0]


def test_unresolved_reference_error_details():
    """
    Failed reference resolution reports the grammar file, the rule, the
    line and the searched namespaces in a deterministic order.
    """
    messages = []
    for _ in range(2):
        with pytest.raises(TextXSemanticError) as e:
            mm_of(os.path.join("err", "badref.tx"))
        messages.append(str(e.value))

    assert e.value.filename == os.path.join(current_dir, "err", "badref.tx")
    assert e.value.line == 4
    message = messages[0]
    assert 'Unexisting rule "Missing"' in message
    assert 'Referenced in rule "Entity"' in message
    assert "Searched namespaces in order" in message
    assert 'namespace "badref" (current grammar)' in message
    assert 'namespace "__base__" (builtins)' in message
    # The searched namespace order is deterministic.
    assert messages[0] == messages[1]


def test_unresolved_qualified_reference_error_details():
    """
    Failed qualified reference resolution reports the alias chain that
    was followed while resolving.
    """
    with pytest.raises(TextXSemanticError) as e:
        mm_of(os.path.join("err", "badref_qualified.tx"))

    assert e.value.line == 4
    message = str(e.value)
    assert 'Unexisting rule "types.Missing"' in message
    assert 'Referenced in rule "Entity"' in message
    assert 'alias "types" -> namespace' in message


def test_duplicate_import_alias_fails():
    """
    Reusing the same import alias in one grammar is an error.
    """
    with pytest.raises(TextXSemanticError) as e:
        mm_of("duplicate_alias.tx")

    assert 'Import alias "types" is already used' in str(e.value)


def test_unknown_alias_in_qualified_reference():
    """
    A qualified reference through an unknown alias reports the failed
    alias lookup in the searched namespaces.
    """
    with pytest.raises(TextXSemanticError) as e:
        mm_of("unknown_alias.tx")

    message = str(e.value)
    assert 'Unexisting rule "nope.Type"' in message
    assert 'alias "nope" in namespace "unknown_alias" (no such alias)' in message
