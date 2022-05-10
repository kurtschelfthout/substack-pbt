from __future__ import annotations

from dataclasses import dataclass, replace
import math
import random
from typing import Any, Callable, Generic, Iterable, Tuple, TypeVar, Union
from example import *

Value = TypeVar("Value", covariant=True)
T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


class Random(Generic[Value]):
    def __init__(self, generate: Callable[[], Value]):
        self._generate = generate

    def generate(self) -> Value:
        return self._generate()

def sample(gen: Random[T]) -> list[T]:
    return [gen.generate() for _ in range(5)]

def constant(value:T) -> Random[T]:
    return Random(lambda: value)

pie = constant(math.pi)

def int_between(low: int, high: int) -> Random[int]:
    return Random(lambda: random.randint(low, high))

ages = int_between(0,100)

def map(f: Callable[[T], U], gen: Random[T]) -> Random[U]:
    return Random(lambda: f(gen.generate()))

letters = map(chr, int_between(ord('a'), ord('z')))

def mapN(f: Callable[...,T], gens: Iterable[Random[Any]]) -> Random[T]:
    return Random(lambda: f(*[gen.generate() for gen in gens]))

# with mapN we gain some more power
def list_of_length(l: int, gen: Random[T]) -> Random[list[T]]:
    gen_of_list = mapN(lambda *args: list(args), [gen] * l)
    return gen_of_list

# we can now write a simple Person generator
simple_names = map("".join, list_of_length(6, letters))
persons = mapN(Person, (simple_names, ages))

# with bind we gain yet more power - conventional wisdom says "anything is possible" with bind,
# but there be dragons (e.g. tail recursion issues)
# also: we can write map with bind but not the other way around 
# also: it's like nested loops where the inner loop can depend on the value of the outer loop,
# and we can keep nesting as many times as we want. With map and mapN we are "stuck" in the same 
# dimension, with bind we can add as many dimensions as we want. But the library loses visibility of
# what the dependencies are between them.
def bind(f: Callable[[T], Random[U]], gen: Random[T]) -> Random[U]:
    # note the lambda and application is important here - we need to return a generator
    # that generates a new value every time it is called. If we'd just return f(gen()),
    # gen would only be called once, and so we'd only generate random Us for a single random T.
    return Random(lambda: f(gen.generate()).generate())

def bindN(f: Callable[...,Random[T]], gens: Iterable[Random[Any]]) -> Random[T]:
    return Random(lambda: f(*[gen.generate() for gen in gens]).generate())

# now we can do things like generate a list of randomly chosen length
def list_of(gen: Random[T]) -> Random[list[T]]:
    length = int_between(0, 10)
    return bind(lambda l: list_of_length(l, gen), length)

lists_of_person = list_of(persons)

def choice(from_gens: Iterable[Random[Any]]) -> Random[Any]:
    all = tuple(from_gens)
    which_gen = int_between(0, len(all)-1)
    return bind(lambda i: all[i], which_gen)

# let's put this together and make a simple property-based testing library

# we need a way for the user to give us a generator and a property, i.e. a function
# which we will then run 100 times and print the the result

# the function to define such a property is usually called "for all", because it reads
# nicely: "for all" "lists l" "the reverse of the reverse of l is l"

# we'll also assume - for simplicity and without any real loss of generality -
# that a a property return a bool True if the property holds, False if not.
# more traditionally you'd use assert and exception, which can also be made to work straightforwardly,
# but this makes the story a bit clearer imo.

# A property is then just a generator of booleans - the idea is we generate the bool
# from this 100 times, or until it generates False, at which point we fail the test.
Property1 = Random[bool]

# first attempt - is this enough?
def for_all_1(gen: Random[T], property: Callable[[T], bool]) -> Property1:
    return map(property, gen)

rev_of_rev_1 = for_all_1(list_of(letters), lambda l: list(reversed(list(reversed(l)))) == l)

sort_by_age_1 = for_all_1(lists_of_person, lambda persons_in: is_valid(persons_in, sort_by_age(persons_in)))

wrong_sort_by_age_1 = for_all_1(lists_of_person, lambda persons_in: is_valid(persons_in, wrong_sort_by_age(persons_in)))

def test_1(property: Property1):
    for test_number in range(100):
        if not property.generate():
            print(f"Fail: at test {test_number}.")
            return
    print("Success: 100 tests passed.")

# what if we want to write for_all over multiple arguments?
# e.g. if I add an integer to each element of a list, then its sum will change by length of the list * integer
# this doesn't work without a slightly smarter for_all
def for_all_2(gen: Random[T], property: Callable[[T], Union[Property1,bool]]) -> Property1:
    def property_wrapper(value: T) -> Property1:
        outcome = property(value)
        if isinstance(outcome, bool):
            return constant(outcome)
        else:
            return outcome
    return bind(property_wrapper, gen)

sum_of_list_2 = for_all_2(list_of(int_between(-10,10)), lambda l: for_all_2(int_between(-10,10), lambda i: sum(e+i for e in l) == sum(l) + len(l) * i))

# now we might think this would be better/more pythonic variant with variadic args - but this is slightly less
# powerful - for_all is really like bind, while for_allN is like mapN. For example, with for_all you can generate
# a random value and then make any of the inner generators depend on that value. 
def for_allN(gens: Iterable[Random[Any]], property: Callable[..., Union[bool, Property1]]) -> Property1:
    ...

# doesn't make a lot of sense but impossible to write with for_allN
weird_sum_of_list = for_all_2(int_between(-10,10), lambda i: for_all_2(list_of(constant(i)), lambda l: sum(e+i for e in l) == sum(l) + len(l) * i))

wrong_2 = for_all_2(list_of(letters), lambda l: list(reversed(l)) == l)

# ok, but let's try to make it print on which values it failed - this needs a change to for_all, and the
# type of property.

@dataclass(frozen=True)
class TestResult:
    is_success: bool
    arguments: Tuple[Any,...]

Property = Random[TestResult]

def for_all(gen: Random[T], property: Callable[[T], Union[Property,bool]]) -> Property:
    def property_wrapper(value: T) -> Property:
        outcome = property(value)
        if isinstance(outcome, bool):
            return constant(TestResult(is_success=outcome, arguments=(value,)))
        else:
            return map(lambda inner_out: replace(inner_out, arguments=(value,) + inner_out.arguments),outcome)
    return bind(property_wrapper, gen)

def test(property: Property):
    for test_number in range(100):
        result = property.generate()
        if not result.is_success:
            print(f"Fail: at test {test_number} with arguments {result.arguments}.")
            return
    print("Success: 100 tests passed.")
    
wrong = for_all(list_of(letters), lambda l: list(reversed(l)) == l)
rev_of_rev = for_all(list_of(letters), lambda l: list(reversed(list(reversed(l)))) == l)
sum_of_list = for_all(list_of(int_between(-10,10)), lambda l: 
                for_all(int_between(-10,10), lambda i: 
                    sum(e+i for e in l) == sum(l) + len(l) * i))
prop_sort_by_age = for_all(lists_of_person, lambda persons_in: is_valid(persons_in, sort_by_age(persons_in)))

prop_wrong_sort_by_age = for_all(lists_of_person, lambda persons_in: is_valid(persons_in, wrong_sort_by_age(persons_in)))
