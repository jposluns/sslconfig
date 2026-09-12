#!/usr/bin/env python3
"""Regression cases for the two convention gates, one per demonstrated review finding.

Round after round of cross-family review broke these gates, and several of those rounds
broke something an earlier round had fixed. Counts are deliberately absent: every version
of this sentence that carried one went stale within a round or two, which is the same drift
these gates exist to catch. A word list in a gate is checked by the gate; the gate itself
was not checked by anything. This file is that check.

Every case below is an input a reviewer actually constructed and ran, not a case imagined
while writing the gate. MISSES are inputs that are real defects and must be caught. FALSE
ALARMS are legitimate text that must not be. The comment on each says which round found it,
so a future change that reintroduces one lands on a named prior finding rather than a
nameless assertion. One case covers a longer adverbial suffix that the engine reaches by backtracking, a shorter
alternative having matched first and failed its word boundary. An earlier version of this paragraph
claimed the case therefore guarded the alternation's ORDER. A reviewer reordered the alternatives
longest first and all cases still passed, so that claim was wrong: what the case actually guards is
that the suffix is NAMED at all, and it fails when the alternative is removed. The correction is
recorded here rather than quietly made, because a file whose subject is overclaiming should show its
own.

Not every case here records a change. One is labelled a coverage guard: `minimise` is caught both
before and after the round that moved its stem from one pattern to the other, because only the route
changed. It fails only if the stem is dropped from BOTH patterns, which is how an incomplete move
would go wrong, so it guards something real without being a regression case. It is labelled that way
because seven of the eight cases added beside it DO fail against the previous code, and describing
all eight the same way would be the overclaim this file exists to prevent.
The summary line counts the three kinds separately, because a coverage guard closed nothing and a
disclosed limit is still open, and folding either into the closed-findings total would overstate what
this file has actually established.

This is not a proof of correctness. It is a record of what has already gone wrong.

Some cases here record a KNOWN LIMIT rather than a fix. Their description begins "known limit:", they
assert the gate's CURRENT wrong answer, and the gate's own docstring discloses the same thing in
prose. They are counted separately in the success line, because reporting an open false alarm as a
closed finding is the kind of quiet overclaim this whole file exists to prevent.

Two limits of this file itself, named because a reviewer found the first one by mutation
testing rather than by reading. A case whose expectation holds under a BROKEN implementation
guards nothing: one recorded case paired a URL fragment with a harmless flag and passed under
a comment stripper with its position guard removed, so the case it was protecting could have
regressed with a green suite. It now has a twin that fails under that mutation. And these
helpers re-implement `main()`'s per-line glue rather than calling it, so `main()`'s own
wiring, the file filters and the double comment strip, has no coverage here.
That happened a second time in the very round that fixed it: a case added to cover a Markdown
container bug asserted the right answer for the wrong reason, because the fixture's second fence
carried an info string and the broken scanner reached the flag by a different route. A case earns its
place by failing when its bug is restored, and nothing else.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_prose_conventions as prose  # noqa: E402
import check_verify_safety as tls  # noqa: E402


def fenced(body, marker="```bash"):
    """Wrap a command body in a Verify section, the way a guide holds one."""
    close = marker.split("bash")[0].split("python")[0] or "```"
    return f"## Verify\n\n{marker}\n{body}\n{close}\n"


def tls_hits(body, marker="```bash"):
    """Every label the TLS gate reports for a fenced body."""
    hits = []
    for _lineno, line in tls.logical_lines(fenced(body, marker)):
        hits.extend(tls.findings_for(tls.strip_comment(line)))
    return hits


# (description, body, must_be_caught, round_found)
TLS_CASES = (
    # MISSES. Each of these passed a shipped version of the gate.
    ("command substitution holding the insecure command",
     'status=$(curl -k https://example.com/health)', True, 4),
    ("redirection & read as a command separator",
     'curl https://example.com/ 2>&1 -k', True, 4),
    ("escaped quote swallowing the rest of the line",
     'curl -H "X-Note: \\" #note" https://example.com/ -k', True, 4),
    ("three-backtick line inside a four-backtick fence",
     "cat <<'TEXT'\n```\nTEXT\ncurl -k https://example.com/", True, 4),
    ("plain curl -k, the flagship case",
     'curl -k https://example.com/health', True, 1),
    ("flag abutting a closing paren",
     '(curl https://example.com/health --insecure)', True, 3),
    ("line continuation between command and flag",
     'curl https://example.com/health \\\n  --insecure', True, 2),
    ("bare s_client, no trust source at all",
     'openssl s_client -connect example.com:443 </dev/null', True, 2),
    ("s_client with a trust source but errors not fatal",
     'openssl s_client -connect example.com:443 -CAfile ca.pem </dev/null', True, 2),
    ("s_client verifying the chain but binding no name",
     'openssl s_client -connect example.com:443 -CAfile ca.pem '
     '-verify_return_error </dev/null', True, 3),
    ("inspection pipe no longer launders an unverified handshake",
     'openssl s_client -connect example.com:443 </dev/null | openssl x509 -noout -text',
     True, 3),
    ("redirect glued to the verifying flag",
     'openssl s_client -connect example.com:443 -CAfile ca.pem -verify_hostname '
     'example.com -verify_return_error</dev/null', False, 3),
    ("quoted parenthesis inside a command substitution",
     'curl -o "$(printf %s \'(\')" https://example.com/ -k', True, 5),
    ("fenced block inside a block quotation",
     "PLACEHOLDER_BLOCKQUOTE", True, 5),
    # A KNOWN LIMIT, disclosed in the docstring rather than fixed: quote state is tracked
    # per physical line, so a quotation spanning a line break hides what follows it.
    ("known limit: quotation spanning a line break",
     "curl --data-binary 'first line\n# second line' -k https://example.com/", False, 5),
    ("a flag after a URL fragment, which comment stripping must not eat",
     'curl https://example.com/#health -k', True, 5),
    ("a flag immediately before a closing quote",
     "ssh deploy@host 'curl https://example.com/health -k'", True, 5),
    ("a flag glued to a redirect",
     'curl -sf https://example.com/health -k>/dev/null', True, 5),
    ("a flag after a quoted query string, which a quote-blind splitter would sever",
     "curl 'https://example.com/?a=1&b=2' -k", True, 6),
    ("a block quotation that ends before its fence does",
     "PLACEHOLDER_BQ_ENDS", True, 8),
    ("a fenced block inside nested block quotations",
     "PLACEHOLDER_BQ_NESTED", True, 6),
    ("curl short flags combined with a digit flag",
     'curl -k4 https://example.com/health', True, 9),
    ("curl short flags combined with the progress-bar flag",
     'curl -k# https://example.com/health', True, 9),
    ("s_client binding an email SAN rather than the endpoint",
     'openssl s_client -connect mq.example.com:5671 -CAfile ca.pem '
     '-verify_return_error -verify_email ops@example.com', True, 9),
    ("a quoted flag token",
     "curl '-k' https://example.com/", True, 10),
    ("a double-quoted flag token",
     'curl "-k" https://example.com/', True, 10),
    ("a git flag that really does disable verification is still caught",
     "git -c http.sslVerify=false clone https://example.com/r.git", True, 10),
    ("a search tool handed something to run",
     "git grep --open-files-in-pager='curl -k https://example.com/' certificate", True, 13),
    ("a wget prefix abbreviation shorter than the full flag",
     "wget --no-check https://example.com/", True, 15),

    # FALSE ALARMS. Each of these was legitimate text a shipped version rejected.
    ("sort -k inside a quoted command substitution",
     'curl https://example.com/ -o "$(sort -k 2 paths.txt)"', False, 4),
    ("sort -k inside an unquoted command substitution",
     'curl -sf -o $(sort -k 2) https://example.com/health', False, 3),
    ("backslash inside single quotes is not an escape",
     "curl -H 'X-Path: \\' https://example.com/; sort -k 2 paths.txt", False, 4),
    ("a comment ends the continuation it terminates",
     'curl https://example.com/ \\\n# no additional arguments\nsort -k 2 paths.txt',
     False, 4),
    ("query-string ampersand does not sever the flag",
     "curl 'https://example.com/?a=1&b=2' -sf", False, 3),
    ("URL fragment survives comment stripping",
     'curl -sf https://example.com/#health', False, 2),
    ("a fully specified s_client is the good state",
     'openssl s_client -connect example.com:443 -CAfile ca.pem '
     '-verify_hostname example.com -verify_return_error </dev/null', False, 3),
    ("s_client -help is not a handshake",
     'openssl s_client -help', False, 2),
    ("quoted closing parenthesis ends the substitution early",
     'curl -o "$(printf %s \')\'; sort -k 2 paths.txt)" https://example.com/', False, 5),
    ("backtick command substitution is lifted out too",
     'curl -o "`sort -k 2 paths.txt`" https://example.com/', False, 5),
    ("an escaped redirection operator is a filename",
     'curl https://example.com/ -o \\>& sort -k 2 paths.txt', False, 5),
    ("a doubled backslash is a literal argument, not a continuation",
     'curl https://example.com/ -o \\\\\n sort -k 2 paths.txt', False, 5),
    ("a fully verified s_client inside a quoted remote command",
     "ssh probe@host 'openssl s_client -connect mq.example.com:5671 -CAfile ca.pem "
     "-verify_hostname mq.example.com -verify_return_error'", False, 5),
    ("prose after a block quotation that ended mid-fence",
     "PLACEHOLDER_BQ_PROSE", False, 8),
    # NOT a bypass, and recorded so it is not "fixed" into a false positive later. A reviewer
    # reported that a blank line after a continuation hides the flag. Tested in bash: `curl \`
    # then a blank line then `-k https://host/` runs curl with NO arguments and then tries to
    # run `-k` as a command. Two commands, which is exactly what the scanner sees.
    ("a blank line after a continuation really is two commands",
     'curl \\\n\n  -k https://example.com/', False, 9),
    ("an audit command that searches for the flag",
     "grep -rn 'curl -k' /etc/cron.d", False, 10),
    ("a git history search for the pattern",
     "git log -S 'rejectUnauthorized: false' -- src/", False, 10),
    ("quoted s_client flags are still the flags",
     "openssl s_client -connect example.com:443 '-verify_hostname' example.com "
     "'-verify_return_error'", False, 13),
    ("a wrapper command's own -k, before the curl it does not belong to",
     "timeout -k 5 30 curl -sf https://example.com/health", False, 15),
    ("the same, through ssh",
     "ssh -k deploy@host 'curl -sf https://example.com/health'", False, 15),
    ("the glued form of the git pickaxe is still a search",
     "git log -Shttp.sslVerify=false -- src/", False, 15),
)


def prose_hits(text):
    """Every finding the prose gate reports for a whole file body."""
    found = []
    fences = prose.Fences()
    for lineno, line in enumerate(text.splitlines(), 1):
        if fences.feed(line):
            continue
        quoted = not fences.inside and line.lstrip().startswith(">")
        is_prose = not (fences.inside or quoted)
        target = line if is_prose else ("" if quoted else prose._fence_comment(line))
        blanked = prose.unquoted(target)
        if prose.ISE_RE.search(blanked) or prose.ISE_NOUNLIKE_RE.search(blanked):
            found.append((lineno, "spelling"))
        if prose.bad_placeholder(line):
            found.append((lineno, "placeholder"))
    return found


# (description, file body, must_be_caught, round_found)
PROSE_CASES = (
    # MISSES.
    ("column-one comment inside a fence",
     "```bash\n# ports are randomised at startup\n```", True, 4),
    ("second placeholder on a line whose first is exempt",
     "curl https://foo.com.example.com/ https://yourdomain.com/", True, 4),
    ("listed stem mid-word",
     "The endpoint is unauthorised by default.", True, 3),
    ("the -ability suffix of a listed stem",
     "Kafka offers serialisability across partitions.", True, 3),
    ("placeholder inside a fenced command, the defect the gate exists for",
     "```bash\n./pocketbase serve yourdomain.com\n```", True, 2),
    ("trailing comment inside a fence",
     "```bash\ncurl https://example.com/  # tokens are randomised\n```", True, 3),
    ("a URL just inside a closing quotation mark",
     'The vendor says "see https://example.com/"; randomised ports are "normal".', True, 5),
    ("a stem added after a reviewer named it",
     "The vendor characterises the endpoint as internal.", True, 10),
    ("emphasise, which needs a suffix to be wrong",
     "They emphasise the default is insecure.", True, 10),
    ("a URL ending against a typographic closing quote",
     "The vendor says “see https://example.com/”; randomised ports are “normal”.", True, 13),
    ("an adverbial suffix of a listed stem",
     "The endpoint is recognisably the same one.", True, 15),
    ("a longer adverbial suffix, which the alternation reaches by backtracking",
     "They are organisationally separate.", True, 15),
    ("coverage guard: minimise, whose stem moved between two patterns",
     "They minimise the risk.", True, 15),

    # FALSE ALARMS.
    ("a .internal host whose left label looks like a placeholder",
     "./pocketbase serve yourdomain.com.internal", False, 4),
    ("a host under example.com",
     "curl https://yourdomain.com.example.com/", False, 3),
    ("a quoted Markdown heading in a block quotation",
     "> ## Authorisation", False, 4),
    ("an escaped quote in fenced string data",
     '```bash\nprintf "%s\\n" "a \\" #randomised"\n```', False, 4),
    ("an identifier inside a four-backtick fence",
     "````python\nmarker = '''\n```\n'''\ndef serialise(value):\n    return value\n````",
     False, 4),
    ("an identifier inside an ordinary fence",
     "```python\ndef serialise(value):\n    return value\n```", False, 2),
    ("a British spelling inside a URL",
     "See https://vendor.example/tls#minimise-exposure for the vendor's wording.",
     False, 3),
    ("a full URL with a British-spelled fragment inside a fenced comment",
     "```bash\ncurl -s https://vendor.example/tls  "
     "# see https://vendor.example/tls#minimise-exposure\n```",
     False, 3),
    # A KNOWN LIMIT, recorded rather than fixed: the URL exemption keys on a scheme, so a
    # bare path fragment is read as prose. Exempting bare paths would blank any comment
    # containing a slash, which is most of them. The gate's docstring says so.
    ("known limit: a bare path fragment is not URL-exempt",
     "```bash\ncurl -s https://vendor.example/tls  # see /tls#minimise-exposure\n```",
     True, 5),
    ("a vendor quotation in double quotes",
     'The vendor writes "requests are randomised per connection" on that page.',
     False, 2),
    ("Oxford English keeps analyse",
     "Analyse the output before changing anything.", False, 2),
    ("a multi-backtick inline code span",
     "Use ``serialise(`value`)`` from the vendor API.", False, 5),
    # A KNOWN LIMIT, disclosed in the docstring rather than fixed: inside a fence only a
    # shell-style trailing comment is read as prose, so a `#` inside a Python triple-quoted
    # string is read as one. Fixing it means tracking multiline string state per language.
    ("known limit: a hash inside a fenced triple-quoted string",
     '```python\ntext = """\n# randomised\n"""\n```', True, 5),
    # KNOWN LIMITS, both disclosed in the gate's docstring: the backtick matching here is
    # run-length based rather than CommonMark's maximal-run rule, and these two lines fall
    # on either side of that difference.
    ("known limit: unequal backtick runs hide real prose",
     "Use `a``; randomised ports ``` here.", False, 6),
    ("known limit: unequal backtick runs inside a valid span expose an identifier",
     "Use `printf '%s' '`` ``` serialise'` to print the vendor identifier.", True, 6),
    ("an uppercase URI scheme is still a URL",
     "See HTTPS://example.com/authorisation for vendor documentation.", False, 9),
    ("a placeholder in a URL path is not the hostname",
     "```bash\ncurl -f https://example.com/migration/yourdomain.com\n```", False, 9),
    ("a vendor quotation in typographic double quotes",
     "The vendor says “requests are randomised per connection”.", False, 9),
    ("emphasis, the ordinary noun, is not a British spelling",
     "The emphasis here is on the default.", False, 10),
    ("a placeholder in a URL query is not the hostname",
     "See https://example.com?previous=yourdomain.com for migration details.", False, 13),
    ("de minimis is Latin, not a British spelling",
     "The remaining de minimis exposure is accepted.", False, 15),
)


def main() -> int:
    failures = []

    for desc, body, should_catch, rnd in TLS_CASES:
        SPECIAL = {
            # A fenced block nested inside a block quotation, which `fenced()` cannot build.
            "PLACEHOLDER_BLOCKQUOTE":
                "## Verify\n\n> ```bash\n> curl -k https://example.com/\n> ```\n",
            # The quotation ends while its fence is still open, and an ordinary fenced block
            # follows. Without the container fix the scanner reads the BARE opening fence of
            # the second block as the first one's close, so the flag inside it falls outside
            # any fence and is never scanned. The second fence must carry no info string, or
            # the broken scanner keeps reading the tail as content and finds the flag anyway,
            # which is how the first version of this case came to assert nothing.
            "PLACEHOLDER_BQ_ENDS":
                "## Verify\n\n> ```bash\n> echo ok\n\n```\ncurl -k https://example.com/\n```\n",
            # The mirror image: with the quotation closed, an ordinary paragraph after it is
            # prose and must not be scanned. Without the fix it is read as fence content and
            # reported, which is a false alarm on a guide warning readers against the flag.
            "PLACEHOLDER_BQ_PROSE":
                "## Verify\n\n> ```bash\n> echo ok\n\nNever run curl -k against production.\n",
            # Two levels of quotation marker with a space between them.
            "PLACEHOLDER_BQ_NESTED":
                "## Verify\n\n>  > ```bash\n>  > curl -k https://example.com/\n>  > ```\n",
        }
        if body in SPECIAL:
            doc = SPECIAL[body]
            caught = bool([x for _n, ln in tls.logical_lines(doc)
                           for x in tls.findings_for(tls.strip_comment(ln))])
        else:
            marker = "````bash" if "```\nTEXT" in body else "```bash"
            caught = bool(tls_hits(body, marker))
        if caught != should_catch:
            want = "caught" if should_catch else "clean"
            failures.append(f"TLS (round {rnd}) {desc}: expected {want}, was not")

    for desc, body, should_catch, rnd in PROSE_CASES:
        caught = bool(prose_hits(body))
        if caught != should_catch:
            want = "caught" if should_catch else "clean"
            failures.append(f"prose (round {rnd}) {desc}: expected {want}, was not")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    cases = TLS_CASES + PROSE_CASES
    total = len(cases)
    limits = sum(1 for c in cases if c[0].startswith("known limit:"))
    guards = sum(1 for c in cases if c[0].startswith("coverage guard:"))
    print(f"  ok    {total} recorded review cases behave as recorded: "
          f"{total - limits - guards} findings closed, {guards} coverage "
          f"guard{'' if guards == 1 else 's'}, {limits} disclosed limits still open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
