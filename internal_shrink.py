from __future__ import annotations

import random
from dataclasses import dataclass, replace
from decimal import InvalidOperation
from typing import (Any, Callable, Generic, Iterable, Optional, Tuple, TypeVar,
                    Union)

from example import *

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")

class InvalidReplay(Exception):
    pass

class ChoiceSeq:
    def __init__(self, history: Optional[list[int]] = None) -> None:
        if history is None:
            self._replaying: Optional[int] = None
            self.history: list[int] = []
        else:
            self._replaying = 0
            self.history = history


    def randint(self, low: int, high: int) -> int:
        if self._replaying is None:
            # recording
            result = random.randint(low, high)
            self.history.append(result)
            return result
        else:
            # replaying
            if self._replaying >= len(self.history):
                raise InvalidReplay()
            value = self.history[self._replaying]
            self._replaying += 1
            if value < low or value > high:
                raise InvalidReplay()
            return value

    def replay(self) -> None:
        self._replaying = 0

    def replayed_prefix(self) -> ChoiceSeq:
        if self._replaying is None:
            raise InvalidOperation()
        return ChoiceSeq(self.history[:self._replaying])


class Random(Generic[T]):
    def __init__(self, generator: Callable[[ChoiceSeq], T]):
        self._generator = generator

    def generate(self, choose: ChoiceSeq) -> T:
        return self._generator(choose)

def sample(gen: Random[T]) -> list[tuple[T, list[int]]]:
    choose = ChoiceSeq()
    return [(gen.generate(choose),choose.history) for _ in range(10)]

def constant(value:T) -> Random[T]:
    return Random(lambda _: value)

def int_between(low: int, high: int) -> Random[int]:
    return Random(lambda choose: choose.randint(low, high))

def map(func: Callable[[T], U], gen: Random[T]) -> Random[U]:
    return Random(lambda choose: func(gen.generate(choose)))

def mapN(func: Callable[...,T], gens: Iterable[Random[Any]]) -> Random[T]:
    return Random(lambda choose: func(*[gen.generate(choose) for gen in gens]))

def bind(func: Callable[[T], Random[U]], gen: Random[T]) -> Random[U]:
    return Random(lambda choose: func(gen.generate(choose)).generate(choose))

def shrink_int(value: int) -> Iterable[int]:
    current = abs(value) - 1
    while current > 0:
        yield current
        current = current // 2
    if value != 0:
        yield 0

Gen = Random[T]
@dataclass(frozen=True)
class TestResult:
    is_success: bool
    arguments: Tuple[Any,...]

Property = Gen[TestResult]

def for_all(gen: Gen[T], property: Callable[[T], Union[Property,bool]]) -> Property:
    def property_wrapper(value: T) -> Property:
        outcome = property(value)
        if isinstance(outcome, bool):
            return constant(TestResult(is_success=outcome, arguments=(value,)))
        else:
            return map(lambda inner_out: replace(inner_out, arguments=(value,) + inner_out.arguments),outcome)
    return bind(property_wrapper, gen)

def shrink_candidates(choices: ChoiceSeq) -> Iterable[ChoiceSeq]:
    # this is part of the list shrinker from vintage.py!
    for i,elem in enumerate(choices.history):
        for smaller_elem in shrink_int(elem):
            smaller_history = list(choices.history)
            smaller_history[i] = smaller_elem
            yield ChoiceSeq(smaller_history)


def test(property: Property):
    def do_shrink(choices: ChoiceSeq) -> None:
        for smaller_choice in shrink_candidates(choices):
            try:
                result = property.generate(smaller_choice)
            except InvalidReplay:
                # print(f"Shrinking: didn't work, invalid replay.")
                continue
            if not result.is_success:
                # cool, found a smaller value that still fails - keep shrinking
                print(f"Shrinking: found smaller arguments {result.arguments}")
                do_shrink(smaller_choice.replayed_prefix())
                break
            # print(f"Shrinking: didn't work, smaller arguments {result.arguments} passed the test")
        else:
            choices.replay()
            print(f"Shrinking: gave up at arguments {property.generate(choices).arguments}")

    for test_number in range(100):
        choices = ChoiceSeq()
        result = property.generate(choices)
        if not result.is_success:
            print(f"Fail: at test {test_number} with arguments {result.arguments}.")
            do_shrink(choices)
            return
    print(f"Success: 100 tests passed.")


def list_of_gen(gens: Iterable[Gen[Any]]) -> Gen[list[Any]]:
    return mapN(lambda *args: list(args), gens)

def list_of_length(l: int, gen: Gen[T]) -> Gen[list[T]]:
    gen_of_list = list_of_gen([gen] * l)
    return gen_of_list

def list_of(gen: Gen[T]) -> Gen[list[T]]:
    length = int_between(0, 10)
    return bind(lambda l: list_of_length(l, gen), length)


wrong_sum = for_all(list_of(int_between(-10,10)), lambda l:
                for_all(int_between(-10,10), lambda i: 
                    sum(e+i for e in l) == sum(l) + (len(l) +1) * i))

equality = for_all(int_between(-10,10), lambda l:
                for_all(int_between(-10,10), lambda i: l == i))

ages = int_between(0,100)
letters = map(chr, int_between(ord('a'), ord('z')))
simple_names = map("".join, list_of_length(6, letters))
persons = mapN(Person, (simple_names, ages))
lists_of_person = list_of(persons)

prop_sort_by_age = for_all(
    lists_of_person, 
    lambda persons_in: is_valid(persons_in, sort_by_age(persons_in)))

prop_wrong_sort_by_age = for_all(
    lists_of_person,
    lambda persons_in: is_valid(persons_in, wrong_sort_by_age(persons_in)))

# this doesn't work that well, for the second letter since we shrink by
# halving the value
equality_letters = (
    for_all(letters, lambda l:
        for_all(letters, lambda i: l == i))
)