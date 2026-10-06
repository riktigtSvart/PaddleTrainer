import ast
from pathlib import Path


POLAR_PATH = Path(__file__).parents[1] / "app" / "api" / "routes" / "polar.py"


def _functions():
    tree = ast.parse(POLAR_PATH.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_both_polar_route_endpoints_expose_explicit_validation_mode_flag():
    functions = _functions()
    for name in (
        "inspect_training_session_routes",
        "persist_training_session_route_environment_evidence",
    ):
        args = [arg.arg for arg in functions[name].args.args]
        assert "hydrology_relation_provider" in args
        assert "hydrology_relation_validation_mode" in args


def test_polar_builder_guards_validation_provider_and_passes_opt_in_to_loader():
    source = POLAR_PATH.read_text(encoding="utf-8")
    assert "VALIDATION_HYDROLOGY_RELATION_PROVIDERS" in source
    assert "synthetic validation " in source
    assert "relations are never enabled implicitly" in source
    assert "allow_validation_provider=hydrology_relation_validation_mode" in source
    assert '"hydrology_relation_validation_mode": (' in source
