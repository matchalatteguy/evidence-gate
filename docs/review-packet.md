# Review packet

A review packet is a small Markdown summary generated from a validation result. It includes:

- a computed decision (`approved` or `needs_work`);
- aggregate check counts;
- passed checks, warnings, and failures;
- evidence paths relative to the run directory.

The packet is designed to be pasted into a review issue, release checklist, or local decision note.
It intentionally contains local relative paths only.
