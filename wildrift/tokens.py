"""Generate access tokens, one per person, as an APP_TOKENS line.

    python -m wildrift.tokens alex sam jonas
"""

import secrets
import sys

from wildrift.security import USER_NAME


def main() -> None:
    names = [n.lower() for n in sys.argv[1:]]
    if not names:
        sys.exit("Usage: python -m wildrift.tokens <name> [<name> ...]")
    bad = [n for n in names if not USER_NAME.match(n)]
    if bad:
        sys.exit(f"Names may only use a-z, 0-9, - and _: {', '.join(bad)}")
    tokens = {n: secrets.token_urlsafe(18) for n in names}
    print("APP_TOKENS=" + ",".join(f"{n}:{t}" for n, t in tokens.items()))
    print()
    for n, t in tokens.items():
        print(f"{n}: {t}")


if __name__ == "__main__":
    main()
