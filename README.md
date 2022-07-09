# MiniPBT

This is the example code for the series of posts on property-based testing on my Substack, [Get Code](https://getcode.substack.com/).

There are several variations of a minimal property-based testing library, designed for simplicity and readability.

I've tested it with Python 3.9, no other dependencies necessary.

- example.py: the example that is used throughout
- vintage.py: original simplified QuickCheck-like implementation, without shrinking
- vintage_shrink.py: original simplified QuickCheck-like implementation, with shrinking
- integrated.py: integrated random generation and shrinking, like Clojure's test.check and Hedgehog
- internal_shrink.py: internal shrinking, like Python's Hypothesis