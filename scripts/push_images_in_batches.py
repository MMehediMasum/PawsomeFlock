import os
import subprocess
from pathlib import Path

IMAGES_DIR = Path("public/images")
MAX_BATCH_BYTES = 400 * 1024 * 1024  # প্রতি ব্যাচে সর্বোচ্চ ৪০০ MB


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            total += (Path(root) / f).stat().st_size
    return total


def run(cmd):
    print("> " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print("ERROR:", result.stderr)
        raise SystemExit(1)


def main():
    subfolders = sorted([d for d in IMAGES_DIR.iterdir() if d.is_dir()])
    print(f"Found {len(subfolders)} post-image folders")

    batch = []
    batch_size = 0
    batch_num = 1

    def flush_batch():
        nonlocal batch, batch_size, batch_num
        if not batch:
            return
        for folder in batch:
            run(["git", "add", str(folder)])
        run(["git", "commit", "-m", f"Add images batch {batch_num}"])
        run(["git", "push", "origin", "main"])
        print(f"Batch {batch_num} done: {len(batch)} folders, {batch_size / 1024 / 1024:.1f} MB")
        batch, batch_size = [], 0
        batch_num += 1

    for folder in subfolders:
        size = dir_size(folder)
        if batch_size + size > MAX_BATCH_BYTES and batch:
            flush_batch()
        batch.append(folder)
        batch_size += size

    flush_batch()
    print("All image batches pushed.")


if __name__ == "__main__":
    main()