"""Generate access tokens, one per person, as an APP_TOKENS line, plus a personal sign-in link each.

    python -m wildrift.tokens chocoloco redbuttguy rozhes --url https://your-app.onrender.com

Opening a personal link signs that phone in once; nobody has to type anything.
"""

import argparse
import secrets
import sys

from wildrift.security import USER_NAME


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate access tokens and personal sign-in links.")
    parser.add_argument("names", nargs="*", help="one name per person (a-z, 0-9, - and _)")
    parser.add_argument("--url", help="the app's address, to print a personal link for each person")
    args = parser.parse_args()

    names = [n.lower() for n in args.names]
    if not names:
        sys.exit("Usage: python -m wildrift.tokens <name> [<name> ...] [--url https://your-app.onrender.com]")
    bad = [n for n in names if not USER_NAME.match(n)]
    if bad:
        sys.exit(f"Names may only use a-z, 0-9, - and _: {', '.join(bad)}")

    tokens = {n: secrets.token_urlsafe(18) for n in names}
    print("APP_TOKENS=" + ",".join(f"{n}:{t}" for n, t in tokens.items()))
    print()
    for n, t in tokens.items():
        # The key goes after "#", so browsers never send it to the server or put it in its logs.
        print(f"{n}: {args.url.rstrip('/')}/#key={t}" if args.url else f"{n}: {t}")


if __name__ == "__main__":
    main()
