# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Static validation that a declared public API reaches a Triton kernel."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Iterator, Mapping, Optional, Set, Tuple, Union

from api_contract import normalize_api_kind, parse_metadata


_ALLOCATION_FUNCTIONS = frozenset(
    {
        "empty",
        "empty_like",
        "zeros",
        "zeros_like",
        "ones",
        "ones_like",
        "full",
        "full_like",
    }
)
_TENSOR_TO_TENSOR_METHODS = frozenset(
    {
        "contiguous",
        "detach",
        "permute",
        "reshape",
        "squeeze",
        "transpose",
        "unsqueeze",
        "view",
    }
)
_TENSOR_TO_SCALAR_METHODS = frozenset({"numel"})
_BANNED_TENSOR_METHODS = frozenset(
    {
        "abs",
        "add",
        "amax",
        "amin",
        "argmax",
        "argmin",
        "bmm",
        "clamp",
        "div",
        "exp",
        "matmul",
        "max",
        "mean",
        "min",
        "mm",
        "mul",
        "pow",
        "relu",
        "sigmoid",
        "softmax",
        "sqrt",
        "sub",
        "sum",
    }
)
_BANNED_TORCH_FUNCTIONS = _BANNED_TENSOR_METHODS
_BANNED_FUNCTIONAL_FUNCTIONS = _BANNED_TENSOR_METHODS
STRICT_TRITON_API_CHECK_ENV = "HELIX_STRICT_TRITON_API_CHECK"


@dataclass(frozen=True)
class LaunchPath:
    kernel_name: str
    line: int
    call_chain: Tuple[str, ...]


@dataclass(frozen=True)
class TritonApiCheckResult:
    status: str
    issues: Tuple[str, ...]
    api_name: Optional[str]
    api_kind: Optional[str]
    launch_paths: Tuple[LaunchPath, ...]

    @property
    def ok(self) -> bool:
        return self.status in {"pass", "not_applicable"}

    def as_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "issues": list(self.issues),
                "api_name": self.api_name,
                "api_kind": self.api_kind,
                "launch_paths": [
                    {
                        "kernel_name": item.kernel_name,
                        "line": item.line,
                        "call_chain": list(item.call_chain),
                    }
                    for item in self.launch_paths
                ],
            },
            ensure_ascii=True,
        )


@dataclass(frozen=True)
class _FunctionInfo:
    key: str
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    class_name: Optional[str]


class _ModuleIndex:
    def __init__(self, tree: ast.Module) -> None:
        self._tree = tree
        self.functions: dict[str, _FunctionInfo] = {}
        self.kernels: Set[str] = set()
        self.triton_names: Set[str] = set()
        self.triton_jit_names: Set[str] = set()
        self.torch_names: Set[str] = set()
        self.functional_names: Set[str] = set()
        self.torch_allocation_names: Set[str] = set()
        self.torch_compute_names: Set[str] = set()
        self.functional_compute_names: Set[str] = set()
        self._collect_imports()
        self._collect_functions()

    @property
    def has_triton_signal(self) -> bool:
        return bool(self.triton_names or self.triton_jit_names or self.kernels)

    @staticmethod
    def _add_matching_aliases(node: ast.ImportFrom, matched: object, target_set: set) -> None:
        for alias in node.names:
            if alias.name in matched:
                target_set.add(alias.asname or alias.name)

    def root(self, api_name: str, api_kind: str) -> Optional[_FunctionInfo]:
        if api_kind == "torch-module":
            return self.functions.get(api_name + ".forward")
        return self.functions.get(api_name)

    def resolve_call(self, node: ast.Call, current: _FunctionInfo) -> Optional[_FunctionInfo]:
        if isinstance(node.func, ast.Name):
            return self.functions.get(node.func.id)
        is_self_attr = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        )
        if is_self_attr and current.class_name is not None:
            return self.functions.get(current.class_name + "." + node.func.attr)
        return None

    def launched_kernel(self, node: ast.Call) -> Optional[str]:
        if not isinstance(node.func, ast.Subscript):
            return None
        target = node.func.value
        if isinstance(target, ast.Name):
            if target.id in self.kernels:
                return target.id
            if target.id not in self.functions:
                # An imported Triton kernel has no local decorator to inspect.
                return target.id
        return None

    def _collect_imports(self) -> None:
        for node in self._tree.body:
            if isinstance(node, ast.Import):
                self._collect_plain_import(node)
            elif isinstance(node, ast.ImportFrom):
                self._collect_from_import(node)

    def _collect_plain_import(self, node: ast.Import) -> None:
        targets = (
            ("triton", self.triton_names),
            ("torch", self.torch_names),
            ("torch.nn.functional", self.functional_names),
        )
        for alias in node.names:
            for module_name, target_set in targets:
                if alias.name == module_name:
                    target_set.add(alias.asname or module_name.rsplit(".", 1)[-1])

    def _collect_from_import(self, node: ast.ImportFrom) -> None:
        if node.module == "triton":
            self._add_matching_aliases(node, {"jit"}, self.triton_jit_names)
        elif node.module == "torch":
            self._collect_torch_from_import(node)
        elif node.module == "torch.nn":
            self._add_matching_aliases(node, {"functional"}, self.functional_names)
        elif node.module == "torch.nn.functional":
            self._add_matching_aliases(node, _BANNED_FUNCTIONAL_FUNCTIONS, self.functional_compute_names)

    def _collect_torch_from_import(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "torch":
                self.torch_names.add(alias.asname or "torch")
            elif alias.name in _ALLOCATION_FUNCTIONS:
                self.torch_allocation_names.add(alias.asname or alias.name)
            elif alias.name in _BANNED_TORCH_FUNCTIONS:
                self.torch_compute_names.add(alias.asname or alias.name)

    def _collect_functions(self) -> None:
        for node in self._tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_function(node, None)
            elif isinstance(node, ast.ClassDef):
                self._collect_class_methods(node)

    def _collect_class_methods(self, node: ast.ClassDef) -> None:
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_function(member, node.name)

    def _add_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        class_name: Optional[str],
    ) -> None:
        key = node.name if class_name is None else class_name + "." + node.name
        self.functions[key] = _FunctionInfo(key=key, node=node, class_name=class_name)
        if class_name is None and self._is_triton_kernel(node):
            self.kernels.add(node.name)

    def _is_triton_kernel(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
        return any(self._is_triton_jit_decorator(decorator) for decorator in node.decorator_list)

    def _is_triton_jit_decorator(self, node: ast.expr) -> bool:
        target = node.func if isinstance(node, ast.Call) else node
        if isinstance(target, ast.Name):
            return target.id in self.triton_jit_names
        return (
            isinstance(target, ast.Attribute)
            and target.attr == "jit"
            and isinstance(target.value, ast.Name)
            and target.value.id in self.triton_names
        )


class _PathAnalyzer:
    def __init__(self, index: _ModuleIndex, strict_torch_compute: bool) -> None:
        self._index = index
        self._strict_torch_compute = strict_torch_compute
        self._issues: list[str] = []
        self._launch_paths: list[LaunchPath] = []
        self._visited: Set[str] = set()

    def analyze(self, root: _FunctionInfo) -> Tuple[Tuple[str, ...], Tuple[LaunchPath, ...]]:
        self._visit(root, (root.key,))
        return tuple(self._issues), tuple(self._launch_paths)

    def _visit(self, function: _FunctionInfo, chain: Tuple[str, ...]) -> None:
        if function.key in self._visited:
            return
        self._visited.add(function.key)
        tensor_names = _tensor_argument_names(function.node)
        lambda_names: dict[str, ast.Lambda] = {}
        for node in _iter_function_execution_nodes(function.node):
            if isinstance(node, ast.Assign):
                tensor_names.update(_assigned_tensor_names(node, tensor_names, self._index))
                lambda_names.update(_assigned_lambda_names(node))
                continue
            if isinstance(node, ast.Call):
                self._handle_call_node(node, function, chain, tensor_names, lambda_names)
                continue
            self._check_execution_node(node, function, chain, tensor_names)

    def _handle_call_node(
        self,
        node: ast.Call,
        function: _FunctionInfo,
        chain: Tuple[str, ...],
        tensor_names: Set[str],
        lambda_names: dict[str, ast.Lambda],
    ) -> None:
        kernel = self._index.launched_kernel(node)
        if kernel is not None:
            self._launch_paths.append(
                LaunchPath(kernel_name=kernel, line=node.lineno, call_chain=chain + (kernel,))
            )
            grid_lambda = _launch_grid_lambda(node, lambda_names)
            if grid_lambda is not None:
                self._visit_grid_lambda(grid_lambda, function, chain, tensor_names)
            return
        self._check_execution_node(node, function, chain, tensor_names)

    def _check_execution_node(
        self,
        node: ast.stmt,
        function: _FunctionInfo,
        chain: Tuple[str, ...],
        tensor_names: Set[str],
    ) -> None:
        """Shared checks for one execution node in a function or grid-lambda body."""
        if isinstance(node, ast.Call):
            self._check_call(node, chain, tensor_names)
            target = self._index.resolve_call(node, function)
            if target is not None:
                self._visit(target, chain + (target.key,))
            return
        if (
            self._strict_torch_compute
            and isinstance(node, ast.BinOp)
            and _binop_uses_tensors(node, tensor_names)
        ):
            self._issue(
                node,
                chain,
                "tensor arithmetic is not allowed in a Triton public API path. "
                "Move this computation into a Triton kernel.",
            )

    def _visit_grid_lambda(
        self,
        lambda_node: ast.Lambda,
        function: _FunctionInfo,
        chain: Tuple[str, ...],
        tensor_names: Set[str],
    ) -> None:
        for node in _iter_execution_nodes(lambda_node.body):
            self._check_execution_node(node, function, chain, tensor_names)

    def _check_call(self, node: ast.Call, chain: Tuple[str, ...], tensor_names: Set[str]) -> None:
        if not self._strict_torch_compute:
            return
        path = _call_path(node.func)
        if not path:
            return
        call_name = ".".join(path)
        root = path[0]
        if root in self._index.torch_names:
            name = path[-1]
            if name in _BANNED_TORCH_FUNCTIONS:
                self._issue(
                    node,
                    chain,
                    _torch_compute_issue(call_name, "direct torch computation"),
                )
            return
        if root in self._index.functional_names:
            if path[-1] in _BANNED_FUNCTIONAL_FUNCTIONS:
                self._issue(
                    node,
                    chain,
                    _torch_compute_issue(call_name, "torch.nn.functional computation"),
                )
            return
        if len(path) == 1 and path[0] in self._index.torch_compute_names:
            self._issue(node, chain, _torch_compute_issue(call_name, "direct torch computation"))
            return
        if len(path) == 1 and path[0] in self._index.functional_compute_names:
            self._issue(node, chain, _torch_compute_issue(call_name, "torch.nn.functional computation"))
            return
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _BANNED_TENSOR_METHODS
            and _expression_is_tensor(node.func.value, tensor_names, self._index)
        ):
            self._issue(node, chain, _torch_compute_issue(call_name, "tensor computation method"))

    def _issue(self, node: ast.AST, chain: Tuple[str, ...], message: str) -> None:
        issue = "line {0}: {1} (call chain: {2})".format(
            getattr(node, "lineno", "?"), message, " -> ".join(chain)
        )
        if issue not in self._issues:
            self._issues.append(issue)


def check_triton_api(operator_file: Path, test_file: Path) -> TritonApiCheckResult:
    try:
        source = operator_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(operator_file))
    except (OSError, SyntaxError) as exc:
        return _failure("unable to parse operator file: {0}".format(exc))

    index = _ModuleIndex(tree)
    if not index.has_triton_signal:
        return TritonApiCheckResult("not_applicable", (), None, None, ())

    try:
        metadata = parse_metadata(test_file)
    except OSError as exc:
        return _failure("unable to read test file: {0}".format(exc))
    api_name = metadata.get("api-name")
    api_kind = metadata.get("api-kind")
    if not api_name:
        return _failure("test metadata is missing required api-name", api_name, api_kind)
    if api_kind is None:
        return _failure("test metadata is missing required api-kind", api_name, api_kind)
    try:
        normalized_api_kind = normalize_api_kind(api_kind)
    except ValueError:
        return _failure("test metadata has unsupported api-kind: {0}".format(api_kind), api_name, api_kind)

    root = index.root(api_name, normalized_api_kind)
    if root is None:
        return _failure("operator does not define declared API: {0}".format(api_name), api_name, api_kind)
    issues, launch_paths = _PathAnalyzer(index, _strict_torch_compute_enabled()).analyze(root)
    if issues:
        return TritonApiCheckResult("fail", issues, api_name, api_kind, launch_paths)
    if not launch_paths:
        return _failure(
            "declared API does not reach a recognizable Triton kernel launch",
            api_name,
            api_kind,
        )
    return TritonApiCheckResult("pass", (), api_name, api_kind, launch_paths)


def _failure(
    issue: str,
    api_name: Optional[str] = None,
    api_kind: Optional[str] = None,
) -> TritonApiCheckResult:
    return TritonApiCheckResult("fail", (issue,), api_name, api_kind, ())


def _call_path(node: ast.expr) -> Tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        parent = _call_path(node.value)
        return parent + (node.attr,) if parent else ()
    return ()


def _torch_compute_issue(call_name: str, category: str) -> str:
    return (
        "{0} is {1} and is not allowed in a Triton public API path. "
        "Move this computation into a Triton kernel; keep the wrapper to allocation, "
        "metadata, layout, and kernel launch work."
    ).format(call_name, category)


def _strict_torch_compute_enabled() -> bool:
    return os.environ.get(STRICT_TRITON_API_CHECK_ENV) == "1"


def _tensor_argument_names(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> Set[str]:
    names: Set[str] = set()
    arguments = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
    for argument in arguments:
        if _annotation_mentions_tensor(argument.annotation):
            names.add(argument.arg)
    return names


def _annotation_mentions_tensor(annotation: Optional[ast.expr]) -> bool:
    if annotation is None:
        return False
    return "Tensor" in ast.unparse(annotation)


def _assigned_tensor_names(node: ast.Assign, tensor_names: Set[str], index: _ModuleIndex) -> Set[str]:
    if not _expression_is_tensor(node.value, tensor_names, index):
        return set()
    return {target.id for target in node.targets if isinstance(target, ast.Name)}


def _assigned_lambda_names(node: ast.Assign) -> Mapping[str, ast.Lambda]:
    if not isinstance(node.value, ast.Lambda):
        return {}
    return {target.id: node.value for target in node.targets if isinstance(target, ast.Name)}


def _expression_is_tensor(node: ast.expr, tensor_names: Set[str], index: _ModuleIndex) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tensor_names
    if isinstance(node, ast.Call):
        path = _call_path(node.func)
        if len(path) == 2 and path[0] in index.torch_names and path[1] in _ALLOCATION_FUNCTIONS:
            return True
        if len(path) == 1 and path[0] in index.torch_allocation_names:
            return True
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in _TENSOR_TO_SCALAR_METHODS:
                return False
            if node.func.attr in _TENSOR_TO_TENSOR_METHODS:
                return _expression_is_tensor(node.func.value, tensor_names, index)
    return False


def _binop_uses_tensors(node: ast.BinOp, tensor_names: Set[str]) -> bool:
    return any(
        isinstance(operand, ast.Name) and operand.id in tensor_names
        for operand in (node.left, node.right)
    )


def _launch_grid_lambda(
    node: ast.Call,
    lambda_names: Mapping[str, ast.Lambda],
) -> Optional[ast.Lambda]:
    if not isinstance(node.func, ast.Subscript):
        return None
    grid = node.func.slice
    if isinstance(grid, ast.Lambda):
        return grid
    if isinstance(grid, ast.Name):
        return lambda_names.get(grid.id)
    return None


def _iter_function_execution_nodes(
    function: Union[ast.FunctionDef, ast.AsyncFunctionDef],
) -> Iterator[ast.AST]:
    for statement in function.body:
        yield from _iter_execution_nodes(statement)


def _iter_execution_nodes(node: ast.AST) -> Iterator[ast.AST]:
    if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Lambda)):
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _iter_execution_nodes(child)
