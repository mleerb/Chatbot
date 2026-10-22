# Git identity

- Before every push, verify that the GitHub account used by the push credentials is `mleerb`. If another account is active or the identity cannot be verified, stop and ask the user to switch to `mleerb`; never push using someone else's account, even if it has write access.
- Before committing, check the author name and email separately from GitHub authentication. Do not silently use the server's automatically inferred identity; ask for the intended identity if it is not confirmed.
