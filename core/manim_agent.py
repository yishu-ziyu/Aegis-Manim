import os
import sys
import subprocess
import argparse

# NOTE: In a real production environment, you would use an LLM SDK.
# For this MVP, since we might not have a key, we provide a simulation mode
# where you can paste the prompt to ChatGPT and paste back the code.

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def generate_prompt(user_input):
    system_prompt = read_file("prompts/system_prompt.md")
    full_prompt = f"""
{system_prompt}

# User Request
{user_input}

# Python Code
"""
    return full_prompt

def run_manim(file_path, scene_name):
    # .venv/bin/manim -ql file_path scene_name
    # Assuming we are running from manim-main directory
    cmd = [
        ".venv/bin/manim",
        "-ql", 
        "--media_dir", "media",
        file_path,
        scene_name
    ]
    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd)

def main():
    parser = argparse.ArgumentParser(description="Aegis Manim Generator")
    parser.add_argument("prompt", help="Natural language description of the animation")
    parser.add_argument("--simulate", action="store_true", help="Print prompt and ask for code input manually")
    parser.add_argument("--llm_key", help="API Key for LLM (not implemented in this minimal MVP script yet)")
    
    args = parser.parse_args()
    
    # 1. Construct Prompt
    full_prompt = generate_prompt(args.prompt)
    
    # 2. Get Code
    code = ""
    if args.simulate:
        print("\n" + "="*40)
        print("SIMULATION MODE: COPY THE TEXT BELOW TO YOUR LLM")
        print("="*40 + "\n")
        print(full_prompt)
        print("\n" + "="*40)
        print("PASTE THE GENERATED PYTHON CODE BELOW (End with lines containing only 'EOF'):")
        print("="*40 + "\n")
        
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "EOF":
                    break
                lines.append(line)
            except EOFError:
                break
        code = "\n".join(lines)
    else:
        # TODO: Implement actual LLM call here using openai/anthropic client
        print("Error: For MVP, please use --simulate to verify the prompt flow, unless you add the API call code.")
        return

    # 3. Save Code
    output_filename = "gen_scene.py"
    # Basic cleanup if User pasted markdown blocks
    code = code.replace("```python", "").replace("```", "").strip()
    
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(code)
    
    print(f"\nSaved generated code to {output_filename}")
    
    # 4. Run Manim
    # We assume the class name is GeneratedScene as per system prompt instructions
    run_manim(output_filename, "GeneratedScene")

if __name__ == "__main__":
    main()
