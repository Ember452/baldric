# Session durability: torn lines and atomic writes

**Status:** accepted — 2026-11-06 (branch `chore/p0-contract-baselines`)

Session files are user data. Three writes could previously destroy data instead of
losing the last action:

| Write | Failure |
| --- | --- |
| transcript append | a process killed mid-append leaves a partial last line; the strict reader then refuses to open the session forever |
| session index | `write_text` truncates first, so an interrupted write leaves a partial line; the strict reader then fails the scan, hiding every session in that project |
| HTML/JSONL export | same non-atomic write, so an interrupted export destroys the previous good file |

## Policy: readers tolerate, writers repair

A partial **final** line is the only thing a crash can legitimately leave behind,
so it is the only thing tolerated:

- `entries_from_transcript(text)` returns the entries plus a flag when it had to
  drop the last line. Corruption anywhere else still raises `SessionJsonlError`,
  and `test_jsonl_storage_still_rejects_corruption_before_the_final_line` pins
  that.
- Reading never rewrites the file. `JsonlSessionStorage` logs one warning and
  keeps the parsed prefix.
- Writing repairs first, because appending onto an unterminated line would glue
  the new record onto the old fragment and turn one damaged line into a damaged
  transcript. The repair drops an unparsable tail, and terminates a complete
  record that merely lost its newline.
- The repair runs under the existing exclusive lock and goes through the existing
  atomic replace, so a crash during the repair leaves the previous file intact.

## The index rebuilds itself

`SessionManager._read_index` now skips a damaged line, logs the count, and
rewrites the index from the surviving records. A failed rewrite is logged and the
parsed records are still returned, so a read-only or full disk cannot turn a
damaged index into a read loop.

Writes go through `baldric_coding/utils/atomic.py` (same-directory temp file,
fsync, replace). An interrupted write keeps the previous file byte-identical,
which the manager and export tests assert by failing `os.replace`.

The helper deliberately does not fsync the directory: a crash immediately after
the replace may bring back the previous file, which is a reverted update rather
than a partial one. Transcript batch writes already pay for directory fsync where
they need it, and the encoding invariant (`tests/invariants/`) counts raw
`os.open` calls, so a second copy of that helper would be recorded debt.

## What this does not cover

- A damaged line in the middle of a transcript is still corruption: repair would
  have to guess which record was lost.
- Cross-process append ordering is unchanged; the existing per-session lock still
  serializes writers.
- The session format itself is unchanged, so `tests/expected/session_entries.jsonl`
  does not move.

## Tests

- `tests/coding/session/test_session.py`: torn final line reads and logs;
  appending and batching repair the tail first; a complete final line without a
  newline is kept; middle corruption still raises; a file containing only a torn
  line reads as empty.
- `tests/coding/session/test_session_manager.py`: a damaged index line drops that
  record, keeps the rest, and rewrites the file; a failed replace keeps the
  previous index and leaves no temp file.
- `tests/coding/session/test_session_export.py`: a failed replace keeps the
  previous export.
