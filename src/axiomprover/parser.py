"""Static extraction of annotated functions from Python source.

Everything in this module is purely syntactic (`ast`-based): no user code is
executed. Executing the target file is confined to the falsifier, which only
runs when the user asks for counterexample search.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

SPEC_DECORATORS = {"requires", "ensures", "proof"}

SUPPORTED_TYPES = {"int": "Int", "bool": "Bool"}


class SpecSyntaxError(Exception):
    """The file's contract annotations are malformed (as opposed to the
    function body merely being outside the supported subset)."""


@dataclass
class SpecClause:
    """One `requires`/`ensures` clause, kept as source AST for translation."""

    kind: str  # "requires" | "ensures"
    params: list[str]
    body: ast.expr
    source: str  # pretty-printed lambda body, for reports


@dataclass
class TargetFunction:
    """A function to verify, with its contract, still in AST form."""

    name: str
    params: list[tuple[str, str]]  # (name, python type: "int" | "bool")
    return_type: str
    body: list[ast.stmt]
    requires: list[SpecClause] = field(default_factory=list)
    ensures: list[SpecClause] = field(default_factory=list)
    proof_hint: str | None = None
    lineno: int = 0
    # Every top-level function in the module (contracted or not), so the
    # translator can inline calls to sibling helpers. Helpers are validated
    # lazily — only when a call to one is actually being translated.
    helpers: dict[str, ast.FunctionDef] = field(default_factory=dict)

    @property
    def param_names(self) -> list[str]:
        return [n for n, _ in self.params]


def parse_file(path: str | Path) -> list[TargetFunction]:
    """Return every top-level function in *path* carrying at least one
    `ensures` clause. Functions without contracts are ignored."""
    source = Path(path).read_text(encoding="utf-8")
    return parse_source(source, filename=str(path))


def parse_source(source: str, filename: str = "<string>") -> list[TargetFunction]:
    tree = ast.parse(source, filename=filename)
    helpers = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    targets = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            target = _extract_function(node)
            if target is not None:
                target.helpers = helpers
                targets.append(target)
    return targets


def _extract_function(node: ast.FunctionDef) -> TargetFunction | None:
    requires: list[SpecClause] = []
    ensures: list[SpecClause] = []
    proof_hint: str | None = None

    for dec in node.decorator_list:
        name = _decorator_name(dec)
        if name not in SPEC_DECORATORS:
            continue
        if not isinstance(dec, ast.Call) or len(dec.args) != 1:
            raise SpecSyntaxError(
                f"{node.name}: @{name} takes exactly one positional argument "
                f"(line {dec.lineno})"
            )
        arg = dec.args[0]
        if name == "proof":
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                raise SpecSyntaxError(
                    f"{node.name}: @proof expects a string literal tactic script"
                )
            proof_hint = arg.value
            continue
        if not isinstance(arg, ast.Lambda):
            raise SpecSyntaxError(
                f"{node.name}: @{name} expects a lambda literal so the "
                f"contract can be read statically (line {dec.lineno})"
            )
        clause = SpecClause(
            kind=name,
            params=[a.arg for a in arg.args.args],
            body=arg.body,
            source=ast.unparse(arg.body),
        )
        (requires if name == "requires" else ensures).append(clause)

    if not ensures:
        return None  # nothing to prove

    params = _extract_params(node)
    return_type = _extract_return_type(node)
    fn_param_names = [n for n, _ in params]

    for clause in requires:
        if clause.params != fn_param_names:
            raise SpecSyntaxError(
                f"{node.name}: @requires lambda must take exactly the function "
                f"parameters {fn_param_names}, got {clause.params}"
            )
    for clause in ensures:
        if clause.params != fn_param_names + ["result"]:
            raise SpecSyntaxError(
                f"{node.name}: @ensures lambda must take the function "
                f"parameters plus 'result' ({fn_param_names + ['result']}), "
                f"got {clause.params}"
            )

    return TargetFunction(
        name=node.name,
        params=params,
        return_type=return_type,
        body=node.body,
        requires=requires,
        ensures=ensures,
        proof_hint=proof_hint,
        lineno=node.lineno,
    )


def _decorator_name(dec: ast.expr) -> str | None:
    """Name of a decorator like `ensures(...)` or `axiomprover.ensures(...)`."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _extract_params(node: ast.FunctionDef) -> list[tuple[str, str]]:
    args = node.args
    if args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults:
        raise SpecSyntaxError(
            f"{node.name}: only plain positional parameters without defaults "
            f"are supported"
        )
    params = []
    for a in args.args:
        ty = _annotation_name(a.annotation)
        if ty not in SUPPORTED_TYPES:
            raise SpecSyntaxError(
                f"{node.name}: parameter '{a.arg}' must be annotated as one of "
                f"{sorted(SUPPORTED_TYPES)} (got {ty!r})"
            )
        params.append((a.arg, ty))
    return params


def _extract_return_type(node: ast.FunctionDef) -> str:
    ty = _annotation_name(node.returns)
    if ty not in SUPPORTED_TYPES:
        raise SpecSyntaxError(
            f"{node.name}: return type must be annotated as one of "
            f"{sorted(SUPPORTED_TYPES)} (got {ty!r})"
        )
    return ty


def _annotation_name(annotation: ast.expr | None) -> str | None:
    if annotation is None:
        return None
    if isinstance(annotation, ast.Name):
        return annotation.id
    return ast.unparse(annotation)
