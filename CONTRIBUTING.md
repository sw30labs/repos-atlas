# Contributing

repos-atlas is three Python scripts using only the standard library. Keep the
survey read-only, the generated page self-contained, and model claims separate
from measurements. The [architecture decisions](docs/adr) explain those choices.

## Development

Use Python 3.10+ and Git. No package installation is needed.

```bash
python3 -m unittest -v
python3 atlas.py --demo
```

Open `demo.html` in a browser. Check search, column sorting, tooltips, and both
themes when changing the renderer. Demo data is fictional and safe to share.
Tests create temporary repositories; they do not inspect your project folder or
call a model. CI checks Linux, macOS, and Windows.

Add a regression test for behavior changes. Keep new runtime dependencies out
unless there is a concrete reason the standard library cannot do the job.

## Issues and pull requests

Describe the problem, the expected behavior, and how to reproduce it using a
small fictional example. Include your OS and Python version for bugs. Run the
tests before submitting a pull request and describe what you checked.

Do not attach your real `survey.json`, `review.json`, `index.html`, `domains.json`,
or screenshots of private projects. These can expose repository names, local
paths, authors, README text, and commit subjects. Use the demo or redact a copy.
Report security vulnerabilities according to [SECURITY.md](SECURITY.md).
