
from __future__ import annotations
from copy import copy

from dataclasses import dataclass, replace
import itertools
import random
from typing import Any, Callable, Generic, Iterable, Protocol, TypeVar, Union

from example import Person, is_valid, sort_by_age, wrong_sort_by_age

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")

# class Arbitrary(Generic[Value]):
#     def generate(self) -> Value:
#         ...

#     def shrink(self, value: Value) -> Iterable[Value]:
#         ...

# def shrink_map(f: Callable[[T],U], s: Shrink[T]) -> Shrink[U]:
#     def shrinker(value: U) -> Iterable[U]:
#         for candidate in s(...):
#             yield f(candidate)
#     return shrinker

class Random(Generic[T]):
    def __init__(self, generator: Callable[[], T]):
        self._generator = generator

    def generate(self) -> T:
        return self._generator()

def random_sample(gen: Random[T]) -> list[T]:
    return [gen.generate() for _ in range(10)]

def random_constant(value:T) -> Random[T]:
    return Random(lambda: value)

def random_int_between(low: int, high: int) -> Random[int]:
    return Random(lambda: random.randint(low, high))

def random_map(func: Callable[[T], U], gen: Random[T]) -> Random[U]:
    return Random(lambda: func(gen.generate()))

def random_mapN(func: Callable[...,T], gens: Iterable[Random[Any]]) -> Random[T]:
    return Random(lambda: func(gen.generate() for gen in gens))

def random_bind(func: Callable[[T], Random[U]], gen: Random[T]) -> Random[U]:
    return Random(func(gen.generate()).generate)


class Shrink(Protocol[T]):
    def __call__(self, value: T) -> Iterable[T]:
        ...

def shrink_int(low: int, high: int) -> Shrink[int]:
    target = 0
    if low > 0:
        target = low
    if high < 0:
        target = high
    def shrinker(value: int) -> Iterable[int]:
        if value == target:
            return
        
        half = (value - target) // 2
        current = value - half
        while half != 0 and current != target:
            yield current
            half = (current - target) // 2
            current = current - half
        yield target
    return shrinker


class CandidateTree(Generic[T]):

    def __init__(self, value: T, candidates: Iterable[CandidateTree[T]]) -> None:
        self._value = value
        (self._candidates,) = itertools.tee(candidates, 1)

    @property
    def value(self):
        return self._value

    @property
    def candidates(self):
        return copy(self._candidates)
        

def tree_constant(value: T) -> CandidateTree[T]:
    return CandidateTree(value, tuple())


def tree_from_shrink(value: T, shrink: Shrink[T]) -> CandidateTree[T]:
    return CandidateTree(
        value = value,
        candidates = (
            tree_from_shrink(v, shrink)
            for v in shrink(value)
        )
    )


def tree_map(f: Callable[[T], U], tree: CandidateTree[T]) -> CandidateTree[U]:
    value = f(tree.value)
    candidates = (tree_map(f, candidate) for candidate in tree.candidates)
    return CandidateTree(
        value = value,
        candidates = candidates
    )


def tree_map2(
    f: Callable[[T, U], V], 
    tree_1: CandidateTree[T], 
    tree_2: CandidateTree[U],
) -> CandidateTree[V]:
    
    value = f(tree_1.value, tree_2.value)

    candidates_1 = (
        tree_map2(f, candidate, tree_2)
        for candidate in tree_1.candidates
    )

    candidates_2 = (
        tree_map2(f, tree_1, candidate)
        for candidate in tree_2.candidates        
    )

    return CandidateTree(
        value = value,
        candidates = itertools.chain(
            candidates_1,
            candidates_2
        )
    )


def tree_mapN(f: Callable[..., U], trees: Iterable[CandidateTree[Any]]) -> CandidateTree[U]:
    trees = list(trees)
    value = f([tree.value for tree in trees])

    def _copy_and_set(trees: list[T], i: int, tree: T) -> list[T]:
        result = list(trees)
        result[i] = tree
        return result

    candidates = (
        tree_mapN(f, _copy_and_set(trees, i, candidate))
        for i in range(len(trees))
        for candidate in trees[i].candidates
    )

    return CandidateTree(
        value = value,
        candidates = candidates
    )


def tree_bind(
    f: Callable[[T], CandidateTree[U]],
    tree: CandidateTree[T]
) -> CandidateTree[U]:

    # here we have a choice whether to shrink the T first, or U.
    # Assuming we'd like to get as small as possible as soon as possible (reducing total nb of shrinks),
    # and that a smaller T into property will result in a smaller U, we shrink T first.
    tree_u = f(tree.value)
    candidates = (
        tree_bind(f, candidate)
        for candidate in tree.candidates
    )

    return CandidateTree(
        value = tree_u.value,
        candidates = itertools.chain(
            candidates, 
            tree_u.candidates
        )
    )


Gen = Random[CandidateTree[T]]

def constant(value: T) -> Gen[T]:
    return random_constant(tree_constant(value))

def int_between(low: int, high: int) -> Gen[int]:
    return random_map(lambda v: tree_from_shrink(v, shrink_int(low, high)), random_int_between(low, high))

def map(func: Callable[[T],U], gen: Gen[T]) -> Gen[U]:
    return random_map(lambda tree: tree_map(func, tree), gen)

def mapN(f: Callable[...,T], gens: Iterable[Gen[Any]]) -> Gen[T]:
    return random_mapN(lambda trees: tree_mapN(f, trees), gens)

def list_of_gen(gens: Iterable[Gen[Any]]) -> Gen[list[Any]]:
    return mapN(lambda args: list(args), gens)

def list_of_length(l: int, gen: Gen[T]) -> Gen[list[T]]:
    gen_of_list = list_of_gen([gen] * l)
    return gen_of_list

def bind(func:Callable[[T], Gen[U]], gen: Gen[T]) -> Gen[U]:
    # the same pattern doesn't work:
    # return random_bind(lambda search_tree: search_tree_bind(func, search_tree), gen)
    # because func returns a Random[SearchTree[U]] and search_tree_bind does not know how
    # to deal with Random.
    # We need to get a value out of Random, by generating it:
    def inner_bind(value: T) -> CandidateTree[U]:
        random_tree = func(value)
        return random_tree.generate()
    # this effectively means that while shrinking the outer value, we are randomly re-generating
    # the inner value! Just like we did in vintage as well, in for_all.
    return random_map(lambda tree: tree_bind(inner_bind, tree), gen)

# now we can do things like generate a list of randomly chosen length
def list_of(gen: Gen[T]) -> Gen[list[T]]:
    length = int_between(0, 10)
    return bind(lambda l: list_of_length(l, gen), length)

@dataclass(frozen=True)
class TestResult:
    is_success: bool
    arguments: tuple[Any,...]

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
    def do_shrink(tree: CandidateTree[TestResult]) -> None:
        for smaller in tree.candidates:
            if not smaller.value.is_success:
                # cool, found a smaller value that still fails - keep shrinking
                print(f"Shrinking: found smaller arguments {smaller.value.arguments}")
                do_shrink(smaller)
                break
        else:
            print(f"Shrinking: gave up at arguments {tree.value.arguments}")
        

    for test_number in range(100):
        result = property.generate()
        if not result.value.is_success:
            print(f"Fail: at test {test_number} with arguments {result.value.arguments}.")
            do_shrink(result)
            return
    print("Success: 100 tests passed.")


wrong_sum = for_all(list_of(int_between(-10,10)), lambda l:
                for_all(int_between(-10,10), lambda i: 
                    sum(e+i for e in l) == sum(l) + (len(l) +1) * i))

equality = for_all(int_between(-10,10), lambda l:
                for_all(int_between(-10,10), lambda i: l == i))


ages = int_between(0,100)
letters = map(chr, int_between(ord('a'), ord('z')))
simple_names = map("".join, list_of_length(6, letters))
persons = mapN(lambda a: Person(*a), (simple_names, ages))
lists_of_person = list_of(persons)

prop_sort_by_age = for_all(
    lists_of_person, 
    lambda persons_in: is_valid(persons_in, sort_by_age(persons_in)))

prop_wrong_sort_by_age = for_all(
    lists_of_person,
    lambda persons_in: is_valid(persons_in, wrong_sort_by_age(persons_in)))