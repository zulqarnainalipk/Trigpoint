# Security

TrigPoint is a single-user tool for your own computer. It listens on 127.0.0.1 only, has no sign-in, checks the `Host` header, requires a custom header on every write, and limits request size. It prints a warning if you make it listen on another address. Do not expose it to a network.

Your Earth Engine key file is a password: keep it outside this folder and never publish it.

To report a vulnerability, write to the author (see `CITATION.cff`) instead of opening a public issue.
