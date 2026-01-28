import os
import json
import sys

REGISTRY_PATH = "scene_registry.json"

def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        # Fallback if running from core/ maybe? No, assuming running from root
        if os.path.exists(f"../{REGISTRY_PATH}"):
            return json.load(open(f"../{REGISTRY_PATH}", "r", encoding="utf-8"))
        print(f"Error: Registry file '{REGISTRY_PATH}' not found.")
        return []
    
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    registry = load_registry()
    if not registry:
        return

    while True:
        clear_screen()
        print("==================================================")
        print("      Aegis 课程模板库 (Course Library - Registry)")
        print("==================================================")
        print("请选择要生成的教学视频：\n")

        for item in registry:
            print(f"[{item['id']}] {item['title']}")
            print(f"    - {item['description']}")
            print("-" * 30)
            
        print("[Q] 退出 (Quit)")
        print("==================================================")
        
        choice = input("\n请输入选项 (ID): ").strip().upper()
        
        if choice == 'Q':
            print("感谢使用 Aegis，再见！")
            break
            
        selected = next((item for item in registry if item['id'] == choice), None)
        
        if selected:
            print(f"\n正在准备生成: {selected['title']}...")
            # Command: .venv/bin/manim -ql [file_path] [class_name]
            # Assumes running from project root where .venv is located
            cmd = f".venv/bin/manim -ql {selected['file_path']} {selected['class_name']}"
            print(f"运行指令: {cmd}")
            os.system(cmd)
            input("\n按回车键返回菜单...")
        else:
            input("\n无效选项，按回车重试...")

if __name__ == "__main__":
    # Ensure we are running from root or handle paths
    # If this script is in core/, and execution is from root: python core/course_menu.py
    # Then current CWD is root.
    main()
