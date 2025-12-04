from __future__ import annotations

import ast
import asyncio
import functools
import inspect
import linecache
import typing

import import_expression
from typing_extensions import ParamSpec

T = typing.TypeVar("T")
P = ParamSpec("P")
U = typing.TypeVar("U")


CORO_CODE = """
async def _repl_coroutine({0}):
    import asyncio
    from bson import ObjectId, json_util

    try:
        pass
    finally:
        _async_executor.scope.globals.update(locals())
"""


def executor_function(sync_function: typing.Callable[P, T]) -> typing.Callable[P, typing.Awaitable[T]]:
    @functools.wraps(sync_function)
    async def sync_wrapper(*args: P.args, **kwargs: P.kwargs):
        """
        Asynchronous function that wraps a sync function with an executor.
        """

        loop = asyncio.get_event_loop()
        internal_function = functools.partial(sync_function, *args, **kwargs)
        return await loop.run_in_executor(None, internal_function)

    return sync_wrapper


class AsyncSender(typing.Generic[T, U]):
    __slots__ = ("iterator", "send_value")

    def __init__(self, iterator: typing.AsyncGenerator[T, typing.Optional[U]]):
        self.iterator = iterator
        self.send_value: U | None = None

    def __aiter__(self) -> typing.AsyncGenerator[typing.Tuple[typing.Callable[[typing.Optional[U]], None], T], None]:
        return self._internal(self.iterator.__aiter__())  # type: ignore

    async def _internal(
        self, base: typing.AsyncGenerator[T, typing.Optional[U]]
    ) -> typing.AsyncGenerator[typing.Tuple[typing.Callable[[typing.Optional[U]], None], T], None]:
        try:
            while True:
                value = await base.asend(self.send_value)
                self.send_value = None
                yield self.set_send_value, value
        except StopAsyncIteration:
            pass

    def set_send_value(self, value: typing.Optional[U]):
        self.send_value = value


class KeywordTransformer(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        return node

    def visit_Return(self, node: ast.Return) -> typing.Union[ast.Return, ast.If]:
        if node.value is None:
            return node

        return ast.If(
            test=ast.Constant(value=True, lineno=node.lineno, col_offset=node.col_offset),
            body=[
                ast.Expr(
                    value=ast.Yield(value=node.value, lineno=node.lineno, col_offset=node.col_offset),
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                ),
                ast.Return(value=None, lineno=node.lineno, col_offset=node.col_offset),
            ],
            orelse=[],
            lineno=node.lineno,
            col_offset=node.col_offset,
        )

    def visit_Delete(self, node: ast.Delete) -> ast.If:
        return ast.If(
            test=ast.Constant(value=True, lineno=node.lineno, col_offset=node.col_offset),
            body=[
                (
                    ast.If(
                        # if 'x' in globals():
                        test=ast.Compare(
                            # 'x'
                            left=ast.Constant(value=target.id, lineno=node.lineno, col_offset=node.col_offset),
                            ops=[
                                # in
                                ast.In(lineno=node.lineno, col_offset=node.col_offset)
                            ],
                            comparators=[
                                # globals()
                                self.globals_call(node)
                            ],
                            lineno=node.lineno,
                            col_offset=node.col_offset,
                        ),
                        body=[
                            ast.Expr(
                                # globals().pop('x')
                                value=ast.Call(
                                    # globals().pop
                                    func=ast.Attribute(
                                        value=self.globals_call(node),
                                        attr="pop",
                                        ctx=ast.Load(),
                                        lineno=node.lineno,
                                        col_offset=node.col_offset,
                                    ),
                                    args=[
                                        # 'x'
                                        ast.Constant(value=target.id, lineno=node.lineno, col_offset=node.col_offset)
                                    ],
                                    keywords=[],
                                    lineno=node.lineno,
                                    col_offset=node.col_offset,
                                ),
                                lineno=node.lineno,
                                col_offset=node.col_offset,
                            )
                        ],
                        # else:
                        orelse=[
                            # del x
                            ast.Delete(targets=[target], lineno=node.lineno, col_offset=node.col_offset)
                        ],
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                    )
                    if isinstance(target, ast.Name)
                    else ast.Delete(targets=[target], lineno=node.lineno, col_offset=node.col_offset)
                )
                # for each target to be deleted, e.g. `del {x}, {y}, {z}`
                for target in node.targets
            ],
            orelse=[],
            lineno=node.lineno,
            col_offset=node.col_offset,
        )

    def globals_call(self, node: ast.AST) -> ast.Call:
        return ast.Call(
            func=ast.Name(id="globals", ctx=ast.Load(), lineno=node.lineno, col_offset=node.col_offset),
            args=[],
            keywords=[],
            lineno=node.lineno,
            col_offset=node.col_offset,
        )


def wrap_code(code: str, args: str = "", auto_return: bool = True) -> ast.Module:
    user_code: ast.Module = import_expression.parse(code, mode="exec")  # type: ignore
    mod: ast.Module = import_expression.parse(CORO_CODE.format(args), mode="exec")  # type: ignore

    for node in ast.walk(mod):
        node.lineno = -100_000
        node.end_lineno = -100_000

    definition = mod.body[-1]  # async def ...:
    assert isinstance(definition, ast.AsyncFunctionDef)

    try_block = definition.body[-1]  # try:
    assert isinstance(try_block, ast.Try)

    try_block.body.extend(user_code.body)

    ast.fix_missing_locations(mod)

    KeywordTransformer().generic_visit(try_block)

    if not auto_return:
        return mod

    last_expr = try_block.body[-1]

    if not isinstance(last_expr, ast.Expr):
        return mod

    if not isinstance(last_expr.value, ast.Yield):
        yield_stmt = ast.Yield(last_expr.value)
        ast.copy_location(yield_stmt, last_expr)
        yield_expr = ast.Expr(yield_stmt)
        ast.copy_location(yield_expr, last_expr)

        try_block.body[-1] = yield_expr

    return mod


class Scope:
    __slots__ = ("globals", "locals")

    def __init__(
        self,
        globals_: typing.Optional[typing.Dict[str, typing.Any]] = None,
        locals_: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ):
        self.globals: typing.Dict[str, typing.Any] = globals_ or {}
        self.locals: typing.Dict[str, typing.Any] = locals_ or {}

    def clear_intersection(self, other_dict: typing.Dict[str, typing.Any]):
        for key, value in other_dict.items():
            if key in self.globals and self.globals[key] is value:
                del self.globals[key]
            if key in self.locals and self.locals[key] is value:
                del self.locals[key]

        return self

    def update(self, other: "Scope"):
        self.globals.update(other.globals)
        self.locals.update(other.locals)
        return self

    def update_globals(self, other: typing.Dict[str, typing.Any]):
        self.globals.update(other)
        return self

    def update_locals(self, other: typing.Dict[str, typing.Any]):
        self.locals.update(other)
        return self


class AsyncCodeExecutor:
    __slots__ = ("args", "arg_names", "code", "loop", "scope", "source", "_function")

    def __init__(
        self,
        code: str,
        scope: typing.Optional[Scope] = None,
        arg_dict: typing.Optional[typing.Dict[str, typing.Any]] = None,
        convertables: typing.Optional[typing.Dict[str, str]] = None,
        loop: typing.Optional[asyncio.BaseEventLoop] = None,
        auto_return: bool = True,
    ):
        self.args = [self]
        self.arg_names = ["_async_executor"]

        if arg_dict:
            for key, value in arg_dict.items():
                self.arg_names.append(key)
                self.args.append(value)

        self.source = code

        try:
            self.code = wrap_code(code, args=", ".join(self.arg_names), auto_return=auto_return)
        except (SyntaxError, IndentationError) as first_error:
            if not convertables:
                raise

            try:
                for key, value in convertables.items():
                    code = code.replace(key, value)
                self.code = wrap_code(code, args=", ".join(self.arg_names))
            except (SyntaxError, IndentationError) as second_error:
                raise second_error from first_error

        self.scope = scope or Scope()
        self.loop = loop or asyncio.get_event_loop()
        self._function = None

    @property
    def function(
        self,
    ) -> typing.Callable[..., typing.Union[typing.Awaitable[typing.Any], typing.AsyncGenerator[typing.Any, typing.Any]]]:
        if self._function is not None:
            return self._function

        exec(compile(self.code, "<repl>", "exec"), self.scope.globals, self.scope.locals)  # pylint: disable=exec-used
        self._function = self.scope.locals.get("_repl_coroutine") or self.scope.globals["_repl_coroutine"]

        return self._function

    def create_linecache(self) -> typing.List[str]:
        lines = [line + "\n" for line in self.source.splitlines()]

        linecache.cache["<repl>"] = (
            len(self.source),  # Source length
            None,  # Time modified (None bypasses expunge)
            lines,  # Line list
            "<repl>",  # 'True' filename
        )

        return lines

    def __aiter__(self) -> typing.AsyncGenerator[typing.Any, typing.Any]:
        return self.traverse(self.function)

    async def traverse(
        self, func: typing.Callable[..., typing.Union[typing.Awaitable[typing.Any], typing.AsyncGenerator[typing.Any, typing.Any]]]
    ) -> typing.AsyncGenerator[typing.Any, typing.Any]:
        try:
            if inspect.isasyncgenfunction(func):
                func_g: typing.Callable[..., typing.AsyncGenerator[typing.Any, typing.Any]] = func  # type: ignore
                async for send, result in AsyncSender(func_g(*self.args)):  # type: ignore
                    send((yield result))
            else:
                func_a: typing.Callable[..., typing.Awaitable[typing.Any]] = func  # type: ignore
                yield await func_a(*self.args)
        except Exception:  # pylint: disable=broad-except
            self.create_linecache()

            raise
