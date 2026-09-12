#!/usr/bin/env python3
"""One definition of a fenced code block, shared by the gates that need one.

Two gates used to carry their own fence tracker. They disagreed: one compared the marker
CHARACTER and the other did not, and neither compared the marker LENGTH. Review
demonstrated both halves of that gap. A closing run shorter than the opening run does not
close the block, so a three-backtick line inside a four-backtick fence read as a close and
handed the rest of the block to whichever scanner was watching; the same line read as an
open in the other gate. Both failure directions were shown with real inputs: an insecure
command hidden after the false close, and ordinary Python rejected as prose after it.

CommonMark's rule, which this implements: a fence opens with three or more backticks or
three or more tildes, indented no more than three spaces. It closes on a line whose run
uses the SAME character and is AT LEAST AS LONG, followed by nothing but whitespace. An
opening line may carry an info string; a closing line may not.

https://spec.commonmark.org/0.31.2/#fenced-code-blocks

This is not a Markdown parser. It does not know about list indentation, HTML blocks, or
link reference definitions, and it is not trying to. It answers one question for both
gates in the same way, so that a construction cannot be a fence in one and prose in the
other. A fence indented four or more spaces, which is what a fence nested two list levels
deep looks like, is not recognized. A renderer shows it as code and a reader copies from it,
and no guide in this corpus has one today, so this is disclosed rather than handled.
"""
import re

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


class Fences:
    """Line-by-line fence state. Feed every line in order; ask `inside` after each.

    Usage is deliberately blunt:

        f = Fences()
        for line in text.splitlines():
            if f.feed(line):
                continue        # the line IS a fence marker, not content
            if f.inside:
                ...             # code
            else:
                ...             # prose

    `feed` returns True for an opening or closing marker line, which belongs to neither
    the code nor the prose around it.
    """

    def __init__(self):
        self.char = None
        self.length = 0

    @property
    def inside(self):
        return self.char is not None

    def close(self):
        """Force the block closed, for a container that ended before its fence did."""
        self.char, self.length = None, 0

    def feed(self, line):
        m = FENCE_RE.match(line)
        if not m:
            return False
        run, rest = m.group(1), m.group(2)
        char, length = run[0], len(run)
        if self.char is None:
            # An opening backtick fence may not carry a backtick in its info string,
            # because the info string would be ambiguous with a closing run.
            if char == "`" and "`" in rest:
                return False
            self.char, self.length = char, length
            return True
        if char == self.char and length >= self.length and not rest.strip():
            self.char, self.length = None, 0
            return True
        # A shorter run, a different character, or a trailing info string is CONTENT of
        # the open block, not a close.
        return False
