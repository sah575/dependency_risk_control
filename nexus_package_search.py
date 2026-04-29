#!/usr/bin/env python3
"""Simple Nexus package existence check using the REST Search API."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether a package or package version exists in Nexus Repository."
    )
    parser.add_argument("name", help="Package name to search, for example: axios")
    parser.add_argument(
        "--version",
        help="Exact version to filter, for example: 1.14.0",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Nexus base URL, for example: https://nexus.example.com",
    )
    parser.add_argument(
        "--repository",
        help="Repository name, for example: npm-proxy",
    )
    parser.add_argument(
        "--format",
        default="npm",
        help="Component format. Default: npm",
    )
    parser.add_argument(
        "--user",
        help="Username for basic auth. If given without --password, password is prompted.",
    )
    parser.add_argument(
        "--password",
        help="Password for basic auth.",
    )
    parser.add_argument(
        "--token",
        help="Bearer token for Authorization header.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON items instead of the simplified report.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification.",
    )
    return parser


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def build_search_url(
    base_url: str,
    name: str,
    version: str | None,
    repository: str | None,
    package_format: str | None,
    continuation_token: str | None = None,
) -> str:
    params = {"name": name}
    if version:
        params["version"] = version
    if repository:
        params["repository"] = repository
    if package_format:
        params["format"] = package_format
    if continuation_token:
        params["continuationToken"] = continuation_token

    query = urllib.parse.urlencode(params)
    return f"{normalize_base_url(base_url)}/service/rest/v1/search?{query}"


def make_request(url: str, args: argparse.Namespace) -> dict[str, Any]:
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/json")

    if args.token:
        request.add_header("Authorization", f"Bearer {args.token}")

    password = args.password
    if args.user and password is None:
        password = getpass.getpass("Nexus password: ")

    if args.user and password is not None:
        credentials = f"{args.user}:{password}".encode("utf-8")
        encoded = base64.b64encode(credentials).decode("ascii")
        request.add_header("Authorization", f"Basic {encoded}")

    ssl_context = None
    if args.insecure:
        ssl_context = ssl._create_unverified_context()

    with urllib.request.urlopen(request, context=ssl_context) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_all_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    continuation_token: str | None = None

    while True:
        url = build_search_url(
            base_url=args.base_url,
            name=args.name,
            version=args.version,
            repository=args.repository,
            package_format=args.format,
            continuation_token=continuation_token,
        )
        payload = make_request(url, args)
        items.extend(payload.get("items", []))
        continuation_token = payload.get("continuationToken")
        if not continuation_token:
            break

    return items


def format_row(item: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(item.get("name", "")),
        "version": str(item.get("version", "")),
        "repository": str(item.get("repository", "")),
        "format": str(item.get("format", "")),
        "group": str(item.get("group", "")),
    }


def print_table(items: list[dict[str, Any]]) -> None:
    rows = [format_row(item) for item in items]
    if not rows:
        print("No results found.")
        return

    columns = ("name", "version", "repository", "format", "group")
    widths = {
        column: max(len(column), max(len(row[column]) for row in rows))
        for column in columns
    }

    header = "  ".join(column.ljust(widths[column]) for column in columns)
    separator = "  ".join("-" * widths[column] for column in columns)
    print(header)
    print(separator)
    for row in rows:
        print("  ".join(row[column].ljust(widths[column]) for column in columns))


def print_simple_report(name: str, version: str | None, items: list[dict[str, Any]]) -> None:
    if version:
        print(f"Package: {name}")
        print(f"Version: {version}")
        print(f"Status: {'FOUND' if items else 'NOT FOUND'}")
        if items:
            print_table(items)
        return

    versions = sorted({str(item.get("version", "")) for item in items if item.get("version")})
    repositories = sorted({str(item.get("repository", "")) for item in items if item.get("repository")})

    print(f"Package: {name}")
    print(f"Status: {'FOUND' if items else 'NOT FOUND'}")
    print(f"Match count: {len(items)}")
    if versions:
        print("Versions: " + ", ".join(versions))
    if repositories:
        print("Repositories: " + ", ".join(repositories))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.user and args.token:
        parser.error("Use either basic auth (--user/--password) or --token, not both.")

    try:
        items = fetch_all_items(args)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP error {exc.code}: {body}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"Connection error: {exc.reason}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON response: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(items, indent=2))
    else:
        print_simple_report(args.name, args.version, items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
