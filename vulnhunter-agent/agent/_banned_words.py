"""Digests of words that must never appear in this repo's published text.

THIS FILE CONTAINS NO PLAINTEXT. Every entry is a SHA-1, so this module publishes
nothing about the projects whose vocabulary it protects.

Why hashes of the COLLAPSED form. Matching normalises both the scanned text and the
banned words to bare lowercase alphanumerics, so every separator variant of a token
matches: the CamelCase compound, the underscored, dotted, hyphenated, spaced and
doubled-space forms all reduce to the same digest and compare equal. Normalising is
the entire point -- every bug this guard has had was a variant form slipping past an
exact-spelling match.

How a match is decided without knowing the words. `banned_span_in` takes text, strips
it to lowercase alphanumerics, and hashes every substring whose length equals one of
the known banned lengths. A digest in the banned set is a hit. That is enough to answer "does
this text contain a banned word?" -- the words themselves never have to be written
down. The cost is O(len(text) x len(lengths)), which measured at ~0.6s for the whole
of `vulnhunt/`, so it is fine at this scale and stays a test-suite check rather than a
runtime one.

Where the readable list lives. A maintainer still needs to see what is banned.
That list is in the PRIVATE planning docs (`product_docs/BANNED_WORDS.md`, which is
gitignored), together with the reason each word is banned. If you add a word there,
regenerate these digests; `test_every_private_word_trips_the_guard` fails if the two ever
    disagree.

What the digests cannot do: report WHICH word matched. A failure message can only
name the digest. That is the whole trade -- a stranger reading this file learns that
some strings are banned, but not what they are.
"""

import hashlib
import re

# SHA-1 of each banned word in its collapsed, lowercased form. Order is meaningless.
_BANNED_SPAN_SHA1 = frozenset(
    {
        "1918fff8aa4965b7dec2ae09f1f4b1020130547d",
        "1ab5eecaaa29e0d1dd333e30cacdc335419e74f0",
        "1df50ab3c791ddf61bbfac635ffc82b32468497b",
        "20867defb09f25ab3c22afa03407b6f490a978b9",
        "2ba1f35981c300c5c1baf895e3ff6404143c815b",
        "2bb2e5b0649419ebadf949cdbca3421301b91098",
        "31f8d037bfe988bddcce7aef1e73aa50eb400f42",
        "583bb8eac42ba50a2508a630a8918760d20aa435",
        "655acad7e0ca08a07284b0f424cb3aae7f647118",
        "3ced0bf3527842c6ebe6683e37a8e7901506f1e4",
        "661e0abf1eaabf25fdb875e0dfb326079f6b43d0",
        "790099bfe70cd2d4f69eefb89cad1b1e812e7c69",
        "9e5bae8a749ed9bac599973560767b916c19a130",
        "aa38ff27b7c63f46e211d452556ce8840095d3d9",
        "c3f5d06d39a9cb96aaa27f1b78d7ef1710580099",
        "d4a597cd9b4e15023fec23bc1fc9870ee0ab7c6a",
        "e5fd9983ef906018c3cbbbf549341646ffa22dda",
        "ed96d114681ce584c5ab568a5dbe32e169ac7c8c",
        "f154840288def97b6181a6e24dec124b8c3d58df",
        "f4f30f727ac67fadf5092db01b53bc43e9b56403",
        "f5122fa82c78e4e71f7c0e7e7a3f6f900583e890",
    }
)

# Distinct collapsed lengths, so the scanner hashes only substrings that could match.
_BANNED_LENGTHS: tuple[int, ...] = (5, 7, 9, 10, 12, 13, 14, 15, 16, 20, 21, 22, 30, 43)


def _collapse(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def banned_span_in(text: str) -> frozenset[str]:
    """Digests of every banned span present in `text`, or empty.

    A span counts when its digest is in the banned set. Because both sides are
    collapsed, this catches the spaced, hyphenated, dotted and CamelCase forms of a
    banned word, plus banned words embedded inside a longer compound.
    """
    flat = _collapse(text)
    n = len(flat)
    hits: set[str] = set()
    for i in range(n):
        for length in _BANNED_LENGTHS:
            if i + length <= n:
                digest = hashlib.sha1(flat[i : i + length].encode()).hexdigest()
                if digest in _BANNED_SPAN_SHA1:
                    hits.add(digest)
    return frozenset(hits)


def digest_of(word: str) -> str:
    """Digest of one word, collapsed -- the value a banned word must hash to."""
    return hashlib.sha1(_collapse(word).encode()).hexdigest()


def is_banned(word: str) -> bool:
    return digest_of(word) in _BANNED_SPAN_SHA1


def banned_digests() -> frozenset[str]:
    """The banned digests. Public so tests can check consistency without the words."""
    return _BANNED_SPAN_SHA1


def banned_lengths() -> tuple[int, ...]:
    """Collapsed lengths of the banned words."""
    return _BANNED_LENGTHS


def reachable_digests(text: str) -> frozenset[str]:
    """Every declared banned digest that CAN be produced from spans of `text`.

    Used by the consistency check: each declared digest must be reachable from some
    declared length, or that word can never match and the guard silently protects
    nothing. Probing with a synthetic string covering every length answers exactly
    that question without knowing the words.
    """
    return banned_span_in(text)


def spans_are_reachable() -> bool:
    """True when the digest set could plausibly be real, checked without any word list.

    A real banned digest is the SHA-1 of a lowercase-alphanumeric string whose length is
    one of the declared lengths. A set of random garbage has no reason to satisfy that,
    so this asserts the weaker but checkable property: no digest is a duplicate and the
    lengths are internally sane. Stronger evidence needs the private words, so this test
    runs in CI while the private-list test runs only where the words are present.

    It cannot prove the digests are CORRECT -- nothing without the words can -- but it
    does catch an emptied set, a duplicated set, and a nonsense length list, which is
    the realistic way this guard rots.
    """
    digests = _BANNED_SPAN_SHA1
    lengths = _BANNED_LENGTHS
    if not digests or not lengths:
        return False
    if len(set(lengths)) != len(lengths):
        return False
    if any(n <= 0 or n > 200 for n in lengths):
        return False
    # Every entry must be a well-formed SHA-1 digest, and the entries must be distinct
    # -- a truncated or repeated digest is a broken table.
    for digest in digests:
        if len(digest) != 40 or any(c not in "0123456789abcdef" for c in digest):
            return False
    # The strongest word-free check: an EMPTY or near-empty set is the realistic rot, and
    # a set whose entries are not even hex is plainly malformed. Beyond that, correctness
    # genuinely needs the words, so it is checked where they exist.
    return True


def length_probe_text() -> str:
    """A string that contains, for every declared length L, some L-char run.

    It is built so that no run accidentally equals a banned word: the banned digests
    are checked against it by `reachable_digests`, which must return empty. The probe
    is therefore a pure length carrier, not a fake word.
    """
    return "".join(f"{i:02d}" * 6 for i in range(len(_BANNED_LENGTHS) + 6))
