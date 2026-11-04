import os
import subprocess
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv  # 1. Import load_dotenv

# 2. Load the variables from the .env file into os.environ
load_dotenv()

# 3. Initialize the client (it automatically detects GEMINI_API_KEY from the environment)
client = genai.Client()

def generate_ffmpeg_command(user_prompt: str, input_file: str, output_file: str, max_retries: int = 4) -> str:
    system_instruction = (
        "You are an expert FFmpeg command-line generator. "
        "Given a user request, output ONLY the raw, valid FFmpeg command arguments "
        "without markdown code blocks, explanations, or 'ffmpeg' prefix. "
        f"Use input file '{input_file}' and output file '{output_file}'."
    )
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                )
            )
            return response.text.strip()
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                wait_time = 2 ** attempt  # Waits 1s, 2s, 4s, 8s
                print(f"[!] API overloaded. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise e  # Re-raise if it's a different error (like a 403 or 401)
                
    raise Exception("API is completely unavailable after multiple retries. Try again later.")

def run_ffmpeg_job(user_prompt: str, input_filename: str, output_filename: str):
    # 1. Use the container's internal paths, NOT the WSL host paths
    input_path = f"/data/input/{input_filename}"
    output_path = f"/data/output/{output_filename}"

    print(f"[*] Analyzing request with Gemini: '{user_prompt}'")
    cmd_args = generate_ffmpeg_command(user_prompt, input_path, output_path)
    print(f"[+] Generated FFmpeg command arguments: {cmd_args}")

    # 2. Prepend kubectl exec to run it inside the Kubernetes pod
    full_command = ["kubectl", "exec", "-i", "ffmpeg-test-pod", "--", "ffmpeg", "-y"] + cmd_args.split()
    
    print("[*] Dispatching job to Kubernetes pod 'ffmpeg-test-pod'...")
    result = subprocess.run(full_command, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"[✓] Success! Processed video saved to cluster volume.")
        print(f"    Check WSL host path: /home/doreen/ffmpeg-data/output/{output_filename}")
    else:
        print(f"[✗] Kubernetes execution failed:\n{result.stderr}")

if __name__ == "__main__":
    # Example test execution
    prompt = "Compress this video for web streaming and lower the resolution to 720p"
    run_ffmpeg_job(prompt, "file_example_MP4_1920_18MG.mp4", "compressed_file_example_MP4_1920_18MG.mp4")