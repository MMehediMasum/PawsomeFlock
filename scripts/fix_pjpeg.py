import os
from pathlib import Path

IMAGES_DIR = Path("public/images")
BLOG_DIR = Path("src/content/blog")

def main():
    renamed = 0
    conflicts = []

    # ধাপ ১: সব .pjpeg ফাইল খুঁজে .jpeg-এ রিনেম করুন
    for root, _dirs, files in os.walk(IMAGES_DIR):
        for fname in files:
            if fname.lower().endswith(".pjpeg"):
                old_path = Path(root) / fname
                new_name = fname[: -len(".pjpeg")] + ".jpeg"
                new_path = Path(root) / new_name

                if new_path.exists():
                    conflicts.append(str(old_path))
                    continue

                old_path.rename(new_path)
                renamed += 1

    print(f"Renamed {renamed} files (.pjpeg -> .jpeg)")
    if conflicts:
        print(f"Skipped {len(conflicts)} files due to naming conflict:")
        for c in conflicts:
            print("  " + c)

    # ধাপ ২: সব পোস্টের লেখায় .pjpeg রেফারেন্স .jpeg দিয়ে বদলান
    updated_files = 0
    for md_path in BLOG_DIR.glob("*.md"):
        text = md_path.read_text(encoding="utf-8")
        if ".pjpeg" in text:
            new_text = text.replace(".pjpeg", ".jpeg")
            md_path.write_text(new_text, encoding="utf-8")
            updated_files += 1

    print(f"Updated references in {updated_files} post files")


if __name__ == "__main__":
    main()