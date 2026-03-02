from __future__ import annotations

import logging
import random
import secrets
import string

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

MIN_VALUE = 0
MAX_VALUE = 2**32 - 1


class RNG:
    def __init__(self):
        """Random Number Generator (RNG) class that provides methods for generating random integers, floats, and strings.

        >>> rng = RNG()
        """
        seed = int.from_bytes(secrets.token_bytes(16), "big")

        self.__seed = seed
        self.random = random.Random(self.__seed)

    @property
    def seed(self) -> int:
        """Get the current seed value."""
        return self.__seed

    @seed.setter
    def seed(self, value: int):
        """Set a new seed value for the RNG. Changing the seed may lead to non-deterministic behavior, so use with caution."""
        logger.warning("Changing the RNG seed may lead to non-deterministic behavior. Use with caution.")
        self.__seed = value
        self.random.seed(value)

    def random_int(self, *, start: int = MIN_VALUE, end: int = MAX_VALUE) -> int:
        """Generate a random integer between `start` and `end` (inclusive).

        >>> rng = RNG()
        >>> number = rng.random_int(start=1, end=10)
        >>> 1 <= number <= 10
        True
        """
        if start > end:
            raise ValueError("Start value must be less than or equal to end value.")

        return self.random.randint(start, end)

    def random_float(self, *, start: float = 0.0, end: float = 1.0) -> float:
        """Generate a random float between `start` and `end`. The `start` value is inclusive, while the `end` value is exclusive.

        >>> rng = RNG()
        >>> number = rng.random_float(start=0.0, end=1.0)
        >>> 0.0 <= number < 1.0
        True
        """
        if start >= end:
            raise ValueError("Start value must be less than end value.")

        return start + (end - start) * self.random.random()

    def random_string(self, length: int = 16, /, *, include_digits: bool = True) -> str:
        """Generate a random string of the specified length. By default, the string includes both letters and digits, but you can choose to exclude digits if desired.

        >>> rng = RNG()
        >>> random_str = rng.random_string(10, include_digits=False)
        >>> len(random_str) == 10 and all(c.isalpha() for c in random_str)
        True
        """
        if length <= 0:
            raise ValueError("Length must be a positive integer.")

        chars = string.ascii_letters
        if include_digits:
            chars += string.digits

        return "".join(self.random.choices(chars, k=length))
