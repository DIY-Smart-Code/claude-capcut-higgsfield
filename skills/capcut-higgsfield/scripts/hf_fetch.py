#!/usr/bin/env python3
"""hf_fetch.py - download a finished Higgsfield MCP generation into the work folder and log it.

The Higgsfield MCP returns a result_url for every completed job (jobs_wait / show_generation_by_ids).
This script saves it as <work>/media/<name>.<ext> and appends a row to <work>/manifest.json, so every
file in the edit traces back to its job, model, prompt and credit cost.

  python hf_fetch.py WORK 003 https://.../hf_..._<job>.png --kind image --job <job_id> \
      --model gpt_image_2_5 --credits 0.25 --prompt "watercolor relay room..."
  python hf_fetch.py WORK --summary          # files, retries and credits spent so far

Re-fetching an existing name keeps the old file as a throwaway in media/rejected/ (nothing is deleted),
so retries stay visible and countable.
"""
import argparse, datetime as dt, hashlib, json, os, shutil, sys, urllib.parse, urllib.request

EXT = {"image": ".png", "video": ".mp4", "audio": ".wav"}


def manifest_path(work):
    return os.path.join(work, "manifest.json")


def load(work):
    p = manifest_path(work)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"items": []}


def save(work, m):
    with open(manifest_path(work), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)


def fetch(work, name, url, kind, job, model, prompt, credits, note):
    media = os.path.join(work, "media")
    os.makedirs(media, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or EXT.get(kind, "")
    dest = os.path.join(media, name + ext)
    m = load(work)
    if os.path.exists(dest):
        rej = os.path.join(media, "rejected")
        os.makedirs(rej, exist_ok=True)
        n = 1
        while os.path.exists(os.path.join(rej, f"{name}-take{n}{ext}")):
            n += 1
        shutil.move(dest, os.path.join(rej, f"{name}-take{n}{ext}"))
        for it in m["items"]:
            if it["file"] == os.path.relpath(dest, work).replace("\\", "/") and it.get("status") == "used":
                it["status"] = "rejected"
                it["file"] = f"media/rejected/{name}-take{n}{ext}"
    req = urllib.request.Request(url, headers={"User-Agent": "capcut-higgsfield/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    sha = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    m["items"].append({
        "name": name, "file": os.path.relpath(dest, work).replace("\\", "/"), "kind": kind, "job_id": job,
        "model": model, "prompt": prompt, "credits": credits, "url": url, "sha256": sha,
        "fetched": dt.datetime.now().isoformat(timespec="seconds"), "status": "used", "note": note,
    })
    save(work, m)
    print(dest)


def summary(work):
    items = load(work)["items"]
    used = [i for i in items if i.get("status") == "used"]
    rej = [i for i in items if i.get("status") == "rejected"]
    total = sum(float(i.get("credits") or 0) for i in items)
    by = {}
    for i in items:
        by.setdefault(i.get("model") or "?", [0, 0.0])
        by[i.get("model") or "?"][0] += 1
        by[i.get("model") or "?"][1] += float(i.get("credits") or 0)
    print(f"files in the edit : {len(used)}")
    print(f"throwaways        : {len(rej)}")
    for k, (n, c) in sorted(by.items()):
        print(f"  {k:<22} {n:>3} jobs  {c:>8.2f} credits")
    print(f"credits spent     : {total:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("name", nargs="?")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--kind", choices=["image", "video", "audio"], default="image")
    ap.add_argument("--job", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--credits", type=float, default=0.0)
    ap.add_argument("--note", default="")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        return summary(a.work)
    if not (a.name and a.url):
        sys.exit("need NAME and URL (or --summary)")
    fetch(a.work, a.name, a.url, a.kind, a.job, a.model, a.prompt, a.credits, a.note)


if __name__ == "__main__":
    main()
