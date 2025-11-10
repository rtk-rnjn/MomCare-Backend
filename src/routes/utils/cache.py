from __future__ import annotations

import hashlib
import inspect
import logging
import pickle
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, ParamSpec, Protocol, TypeVar, Union, cast

from redis.asyncio import Redis

ReturnType_co = TypeVar("ReturnType_co", covariant=True)
T = TypeVar("T")
P = ParamSpec("P")

logger = logging.getLogger(__name__)

CACHE_DB = 5

MaybeAwaitable = Union[T, Awaitable[T]]
MaybeAwaitableFunc = Callable[P, "MaybeAwaitable[T]"]


class CacheProtocol(Protocol[ReturnType_co]):

    redis: Redis

    async def __call__(*args: Any, **kwargs: Any) -> ReturnType_co: ...
    async def invalidate(*args: Any, **kwargs: Any) -> None: ...

    @property
    def __name__(self) -> str: ...


async def maybe_coroutine(f: MaybeAwaitableFunc[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    value = f(*args, **kwargs)
    if inspect.isawaitable(value):
        return await value
    else:
        return value


def async_method_cache(*, expire: int | None = None, ignore_kwargs: bool = True) -> Callable[[Callable[P, Coroutine[Any, Any, ReturnType_co]]], CacheProtocol[ReturnType_co]]:
    def decorator(func: Callable[P, Coroutine[Any, Any, ReturnType_co]]) -> CacheProtocol[ReturnType_co]:
        redis = Redis(db=CACHE_DB, decode_responses=False, protocol=3)

        def make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            raw = [func.__module__, func.__qualname__, args]
            if not ignore_kwargs:
                raw.append(tuple(sorted(kwargs.items())))

            data = pickle.dumps(raw, protocol=pickle.HIGHEST_PROTOCOL)
            return hashlib.sha256(data).hexdigest()

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> ReturnType_co:
            fetch_cache = kwargs.pop("fetch_cache", True)
            cache = kwargs.pop("cache", True)

            key = make_key(args[1:], kwargs)

            logger.debug("Checking cache for func=`%s` args=%s kwargs=%s", func.__name__, args[1:], kwargs if not ignore_kwargs else {})

            if fetch_cache:
                data = await maybe_coroutine(redis.get, key)
                if isinstance(data, bytes):
                    result = pickle.loads(data)
                    logger.debug("Cache hit for func=`%s` args=%s kwargs=%s", func.__name__, args[1:], kwargs if not ignore_kwargs else {})
                    return result
            else:
                logger.warning("Fetch_Cache=False for func=`%s` args=%s kwargs=%s. Bypassing cache.", func.__name__, args[1:], kwargs if not ignore_kwargs else {})

            logger.debug("Cache miss for func=`%s` args=%s kwargs=%s. Executing function.", func.__name__, args[1:], kwargs if not ignore_kwargs else {})
            result = await func(*args, **kwargs)

            if cache:
                await maybe_coroutine(redis.set, key, pickle.dumps(result), expire)
            else:
                logger.warning("Caching=False for func=`%s` args=%s kwargs=%s. Not caching result.", func.__name__, args[1:], kwargs if not ignore_kwargs else {})

            return result

        async def invalidate(*args: P.args, **kwargs: P.kwargs) -> None:
            key = make_key(args, kwargs)

            await maybe_coroutine(redis.delete, key)
            logger.debug("Cache invalidated for func=`%s` args=%s kwargs=%s", func.__name__, args, kwargs if not ignore_kwargs else {})

        setattr(wrapper, "invalidate", invalidate)
        setattr(wrapper, "__name__", func.__name__)

        return cast(CacheProtocol[ReturnType_co], wrapper)

    return decorator
