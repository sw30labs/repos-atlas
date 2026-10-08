# Security and privacy

## Data handling

- `survey.py` reads local files and Git metadata. It does not fetch or push.
- `atlas.py` writes a self-contained HTML file with no external assets or requests.
- `review.py` sends a bounded README excerpt, project name, language counts,
  markers, recent commit subjects, and a short file tree to the endpoint you
  select. It accepts loopback HTTP(S) endpoints and exactly one remote endpoint,
  `https://api.openai.com`; it bypasses system proxies and refuses redirects.
- **With the OpenAI endpoint, that evidence leaves your machine** and is subject
  to OpenAI's data handling. Each run prints a `CLOUD:` line before the first
  call. `OPENAI_API_KEY` is read from the environment or the git-ignored `.env`
  and is sent only to `api.openai.com`, never to a local server.
- A local model server may log or forward its requests. Use a server you trust
  and configure it to keep data local. Repository and model text are
  untrusted; model suggestions never execute actions.

Generated inventories and `domains.json` are ignored by Git, but are **not
anonymized**. They can contain private names, paths, authors, and text. Remote URL
userinfo, query strings, and fragments are removed from new surveys; this is not
a general secret scrubber for READMEs, filenames, commit messages, or unusual
remote formats. Review every artifact before sharing it. Publish only the
fictional demo when you need a public example.

Run the tools only on folders you intend to inspect. The line-counting walk does
not implement `.gitignore` rules. Local processes and a local model server remain
inside your trust boundary; OpenAI does not.

## Reporting a vulnerability

Please do not disclose exploit details or private data in a public issue.
Use GitHub's **Security → Report a vulnerability** on this repository when that
option is available. Otherwise, open an issue requesting a private reporting
channel without including technical details; a maintainer can arrange one.

Include the affected revision, impact, and a minimal fictional reproduction in
the private report. Security fixes target the current `main` branch; there is no
promised backport or response-time policy for older tags.
