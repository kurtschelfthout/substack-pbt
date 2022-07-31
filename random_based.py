from __future__ import annotations

from dataclasses import dataclass, replace
import random
from typing import Any, Callable, Generic, Iterable, Optional, Tuple, TypeVar, Union
from example import *

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")

Size = int

class SizeExceeded(Exception):
    pass

class Random(Generic[T]):
    def __init__(self, 
        generator: Callable[[Optional[Size]], Tuple[T, Size]]):
        self._generator = generator

    def generate(self, min_size: Optional[Size] = None) -> Tuple[T, Size]:
        return self._generator(min_size)


def sample(gen: Random[T]) -> list[T]:
    return [gen.generate()[0] for _ in range(10)]

def constant(value:T) -> Random[T]:
    return Random(lambda _: (value, 0))

def dec_size(min_size: Optional[Size], decrease: Size) -> Optional[Size]:
    if min_size is None:
        return None
    smaller = min_size-decrease
    if smaller < 0:
        raise SizeExceeded(f"{min_size=} {decrease=} {smaller=}")
    return smaller

def int_between(low: int, high: int) -> Random[int]:
    def zig_zag(i: int):
        if i < 0:
            return -2*i - 1
        else:
            return 2*i
    def generator(min_size: Optional[Size]):
        value = random.randint(low, high)
        size = zig_zag(value)
        dec_size(min_size, size)
        return value, size
    return Random(generator)

def map(func: Callable[[T], U], gen: Random[T]) -> Random[U]:
    def generator(min_size: Optional[Size]):
        result, size = gen.generate(min_size)
        return func(result), size
    return Random(generator)

def mapN(func: Callable[...,T], gens: Iterable[Random[Any]]) -> Random[T]:
    def generator(min_size: Optional[Size]):
        results: list[Any] = []
        size_acc = 0
        for gen in gens:
            result, size = gen.generate(min_size)
            min_size = dec_size(min_size, size)
            results.append(result)
            size_acc += size
        return func(*results), size_acc
    return Random(generator)

def bind(func: Callable[[T], Random[U]], gen: Random[T]) -> Random[U]:
    def generator(min_size: Optional[Size]):
        result,size_outer = gen.generate(min_size)
        min_size = dec_size(min_size, size_outer)
        result,size_inner = func(result).generate(min_size)
        size = size_inner+size_outer
        return result, size
    return Random(generator)

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

def test(property: Property):
    def find_smaller(min_result: TestResult, min_size: Size):
        skipped, not_shrunk, shrunk  = 0, 0, 0
        while skipped + not_shrunk + shrunk <= 100_000 and min_size > 0:
            try:
                result, size = property.generate(min_size)
                if size >= min_size:
                    skipped += 1
                elif not result.is_success:
                    shrunk += 1
                    min_result, min_size = result, size
                    # print(f"Shrinking: found smaller arguments {result.arguments}")
                else:
                    not_shrunk += 1
                    # print(f"Shrinking: didn't work, smaller arguments {result.arguments} passed the test")
            except SizeExceeded:
                skipped += 1

        print(f"Shrinking: gave up at arguments {min_result.arguments}")
        print(f"{skipped=} {not_shrunk=} {shrunk=} {min_size=}")


    for test_number in range(100):
        result, size = property.generate()
        if not result.is_success:
            print(f"Fail: at test {test_number} with arguments {result.arguments}.")
            find_smaller(result, size)
            return
    print("Success: 100 tests passed.")


# we don't even have to change the definition of letters!
letters = map(chr, int_between(ord('a'), ord('z')))

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
                    sum(e+i for e in l) == sum(l) + (len(l) + 1) * i))

equality = for_all(int_between(-10,10), lambda l:
                for_all(int_between(-10,10), lambda i: l == i))

equality_letters = (
    for_all(letters, lambda l:
        for_all(letters, lambda i: l == i))
)

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
