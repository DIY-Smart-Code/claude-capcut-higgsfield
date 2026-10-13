#!/usr/bin/env python3
"""hf_upload.py - PUT a local file to the presigned upload_url returned by the Higgsfield MCP media_upload tool.

  python hf_upload.py FILE "<upload_url>" [--content-type video/mp4]

Sends Content-Type, and If-None-Match: * when the URL's X-Amz-SignedHeaders lists it (the signature fails
without it). Prints the HTTP status; on 200 call media_confirm with the media_id.
"""
import argparse, mimetypes, sys, urllib.parse, urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("url")
    ap.add_argument("--content-type")
    a = ap.parse_args()
    ctype = a.content_type or mimetypes.guess_type(a.file)[0] or "application/octet-stream"
    signed = urllib.parse.parse_qs(urllib.parse.urlparse(a.url).query).get("X-Amz-SignedHeaders", [""])[0]
    headers = {"Content-Type": ctype, "User-Agent": "curl/8.9.1"}   # Python's default UA is blocked (Cloudflare 1010)
    if "if-none-match" in signed.split(";"):
        headers["If-None-Match"] = "*"
    data = open(a.file, "rb").read()
    req = urllib.request.Request(a.url, data=data, method="PUT", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            print(r.status)
    except urllib.error.HTTPError as e:
        print(e.code, e.read()[:300].decode("utf-8", "replace"))
        sys.exit(1)


if __name__ == "__main__":
    main()
