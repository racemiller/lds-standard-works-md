#!/usr/bin/env python3
"""
generate_conference_urls.py

Generate the list of General Conference *period* URLs to feed into the
scraper's `simple_gcscraper_byperiod.py`. One URL per conference session,
of the form:

    https://www.churchofjesuschrist.org/study/general-conference/YYYY/MM?lang=eng

Notes / assumptions
-------------------
* The online archive runs from 1971 to the present, so 1971 is the default
  start year. Earlier talks aren't available via this path.
* General Conference is held in April (04) and October (10). Those are the
  only two periods generated. (A handful of years had extra sessions, but the
  per-period landing pages use 04/10.)
* For the current year, a conference is only included if it has already
  happened relative to today's date — so you don't generate URLs that 404.
  Override with --end-year / --through if your clock or needs differ.

This intentionally only emits the reliable per-period URLs. The site's
"by decade" groupings (e.g. /20102019) use slugs that vary, so verify those
by hand if you'd rather use the by-10-years scraper.

Examples
--------
    # Everything from 1971 through the most recent conference, to a file:
    python generate_conference_urls.py --out urls.txt

    # Just 2000 onward:
    python generate_conference_urls.py --start-year 2000

    # A fixed range, ignoring today's date:
    python generate_conference_urls.py --start-year 2023 --through 2025/10
"""

import argparse
import datetime as _dt
import sys

BASE = "https://www.churchofjesuschrist.org/study/general-conference"
PERIODS = ("04", "10")  # April, October


def _through_from_today(today: _dt.date) -> tuple[int, str]:
    """Return (year, month) of the most recent conference that has occurred."""
    if today.month >= 10:
        return today.year, "10"
    if today.month >= 4:
        return today.year, "04"
    # before April: last one was October of the previous year
    return today.year - 1, "10"


def generate(start_year: int, end_year: int, end_month: str, lang: str) -> list[str]:
    urls = []
    for year in range(start_year, end_year + 1):
        for period in PERIODS:
            if year == end_year and period > end_month:
                continue
            urls.append(f"{BASE}/{year}/{period}?lang={lang}")
    return urls


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start-year", type=int, default=1971,
                   help="First year to include (default: 1971).")
    p.add_argument("--end-year", type=int, default=None,
                   help="Last year to include (default: current year).")
    p.add_argument("--through", type=str, default=None,
                   help="Stop at this exact YYYY/MM (overrides date awareness).")
    p.add_argument("--lang", default="eng", help="Language code (default: eng).")
    p.add_argument("--out", default=None,
                   help="Write URLs here (default: stdout).")
    args = p.parse_args(argv)

    today = _dt.date.today()

    if args.through:
        try:
            ty, tm = args.through.split("/")
            end_year, end_month = int(ty), tm.zfill(2)
            if end_month not in PERIODS:
                p.error("--through month must be 04 or 10")
        except ValueError:
            p.error("--through must look like YYYY/MM, e.g. 2025/10")
    else:
        default_year, default_month = _through_from_today(today)
        end_year = args.end_year if args.end_year is not None else default_year
        # if the user forced an end year >= the computed one, cap the month
        end_month = "10" if end_year < default_year or args.end_year else default_month
        if args.end_year and args.end_year == default_year:
            end_month = default_month

    if end_year < args.start_year:
        p.error("end year is before start year")

    urls = generate(args.start_year, end_year, end_month, args.lang)

    text = "\n".join(urls) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {len(urls)} URLs to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
