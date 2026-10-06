import ast
from pathlib import Path


POLAR_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "api"
    / "routes"
    / "polar.py"
)


def _module():
    return ast.parse(POLAR_PATH.read_text(encoding="utf-8"))


def _async_function(module, name):
    return next(
        node
        for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )


def test_polar_inspect_and_persist_expose_explicit_relation_provider_parameter():
    module = _module()
    for name in (
        "inspect_training_session_routes",
        "persist_training_session_route_environment_evidence",
    ):
        function = _async_function(module, name)
        arg_names = [arg.arg for arg in function.args.args]
        assert "hydrology_relation_provider" in arg_names


def test_polar_internal_builder_uses_relation_live_projection_before_environment_projection():
    source = POLAR_PATH.read_text(encoding="utf-8")
    assert "build_route_hydrology_relation_live_projection(" in source
    assert "effective_trusted_route_hydrology_context" in source
    trusted_env_call = source.index("build_trusted_route_environment_context(")
    effective_use = source.index(
        "effective_trusted_route_hydrology_context,",
        trusted_env_call,
    )
    assert effective_use > trusted_env_call
    assert "hydrology relation providers are inspect-only in V23.2" in source
