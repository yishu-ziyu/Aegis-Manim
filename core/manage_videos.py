import os
import shutil
import argparse
import glob
from datetime import datetime

# Script is in core/, but intended to be run from root: python core/manage_videos.py
# If run from root, CWD is root.
# WAREHOUSE_DIR relative to root
WAREHOUSE_DIR = "final_video_warehouse"
MEDIA_DIR = "media"

def get_latest_video(scene_name):
    # Search recursively for the scene video in media/videos
    # Pattern: media/videos/*/480p15/SceneName.mp4
    # The intermediate folder might be the python file name, which changed.
    # We search recursively: media/videos/**/SceneName.mp4
    
    # Recursive glob might be needed.
    # Manim 0.17+ structure: media/videos/[FileBaseName]/[Quality]/[SceneName].mp4
    # We just search for the SceneName.mp4 anywhere in media/videos
    
    pattern = f"{MEDIA_DIR}/videos/**/{scene_name}.mp4"
    files = glob.glob(pattern, recursive=True)
    
    # Filter out partial movie files just in case
    files = [f for f in files if "partial_movie_files" not in f]
    
    if not files:
        return None
    
    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def publish_video(scene_name, rename=None):
    if not os.path.exists(WAREHOUSE_DIR):
        os.makedirs(WAREHOUSE_DIR)
        print(f"Created warehouse directory: {WAREHOUSE_DIR}")

    src_path = get_latest_video(scene_name)
    if not src_path:
        print(f"Error: Could not find any rendered video for scene '{scene_name}' in {MEDIA_DIR}/")
        print("Tip: Run the manim render command first.")
        return

    # Determine destination filename
    ext = os.path.splitext(src_path)[1]
    if rename:
        dest_filename = f"{rename}{ext}"
    else:
        dest_filename = os.path.basename(src_path)

    dest_path = os.path.join(WAREHOUSE_DIR, dest_filename)
    
    try:
        shutil.copy2(src_path, dest_path)
        print(f"✅ Success! Video published to: {dest_path}")
        print(f"   Source: {src_path}")
    except Exception as e:
        print(f"❌ Failed to publish video: {e}")

def clean_media(dry_run=False):
    if not os.path.exists(MEDIA_DIR):
        print("Media directory already empty or does not exist.")
        return

    size = 0
    for path, dirs, files in os.walk(MEDIA_DIR):
        for f in files:
            fp = os.path.join(path, f)
            size += os.path.getsize(fp)
    
    size_mb = size / (1024 * 1024)
    
    print(f"Ready to clean {MEDIA_DIR}/ directory.")
    print(f"Total space to free: {size_mb:.2f} MB")
    
    if dry_run:
        print("[Dry Run] No files were deleted.")
        return

    confirm = input("Are you sure you want to delete ALL temporary render files? (y/n): ")
    if confirm.lower() == 'y':
        try:
            shutil.rmtree(MEDIA_DIR)
            print("✅ Cleanup complete. Media directory removed.")
        except Exception as e:
            print(f"❌ Cleanup failed: {e}")
    else:
        print("Cleanup cancelled.")

def list_warehouse():
    print(f"\n📦 Final Video Warehouse ({WAREHOUSE_DIR}/):")
    if not os.path.exists(WAREHOUSE_DIR):
        print("   (Directory not found)")
        return
        
    files = os.listdir(WAREHOUSE_DIR)
    if not files:
        print("   (Empty)")
    else:
        for f in files:
            if not f.startswith("."):
                print(f"   - {f}")
    print("")

def main():
    parser = argparse.ArgumentParser(description="Aegis Video Asset Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Publish Command
    pub_parser = subparsers.add_parser("publish", help="Move a rendered video to the warehouse")
    pub_parser.add_argument("scene_name", help="The Class Name of the scene (e.g., SupplyDemandScene)")
    pub_parser.add_argument("--rename", "-r", help="New name for the file (optional)")

    # Clean Command
    clean_parser = subparsers.add_parser("clean", help="Delete temporary media files")
    clean_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")
    
    # List Command
    subparsers.add_parser("list", help="List files in warehouse")

    args = parser.parse_args()

    if args.command == "publish":
        publish_video(args.scene_name, args.rename)
    elif args.command == "clean":
        clean_media()
    elif args.command == "list":
        list_warehouse()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
