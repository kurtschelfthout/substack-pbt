from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Person:
    name: str
    age: int

    def __post_init__(self):
        if self.age < 0:
            raise ValueError(f"Age must be positive")

def sort_by_age(people: list[Person]) -> list[Person]:
    return sorted(people, key=lambda p: p.age)

def wrong_sort_by_age(people: list[Person]) -> list[Person]:
    # whoops, we forgot the key
    return sorted(people)

def is_valid(persons_in: list[Person], persons_out: list[Person]) -> bool:
    same_length = len(persons_in) == len(persons_out)
    sorted = all(persons_out[i].age <= persons_out[i + 1].age
                for i in range(len(persons_out)-1))
    unchanged = { p.name for p in persons_in } == { p.name for p in persons_out }
    return same_length and sorted and unchanged