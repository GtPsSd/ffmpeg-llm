import os
import subprocess
import time
import uuid
import textwrap
import json
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
    input_path = f"/data/input/{input_filename}"
    output_path = f"/data/output/{output_filename}"

    print(f"[*] Analyzing request with Gemini: '{user_prompt}'")
    cmd_args = generate_ffmpeg_command(user_prompt, input_path, output_path)
    print(f"[+] Generated FFmpeg arguments: {cmd_args}")

    # 1. Create a unique job name
    job_id = str(uuid.uuid4())[:8]
    job_name = f"ffmpeg-job-{job_id}"

    # 2. Dynamically generate the Kubernetes Job YAML safely
    job_yaml = textwrap.dedent(f"""\
        apiVersion: batch/v1
        kind: Job
        metadata:
          name: {job_name}
        spec:
          backoffLimit: 0
          template:
            spec:
              restartPolicy: Never
              containers:
              - name: ffmpeg
                image: jrottenberg/ffmpeg:4.4-alpine
                command: ["/bin/sh", "-c"]
                args: 
                - |
                  ffmpeg -y {cmd_args}
                volumeMounts:
                - mountPath: /data
                  name: ffmpeg-storage
              volumes:
              - name: ffmpeg-storage
                persistentVolumeClaim:
                  claimName: ffmpeg-pvc
    """)
    
    # 3. Save the YAML to a temporary file
    manifest_path = f"{job_name}.yaml"
    with open(manifest_path, "w") as f:
        f.write(job_yaml)
    # 4. Apply the Job to the cluster
    print(f"[*] Dispatching Kubernetes Job '{job_name}'...")
    result = subprocess.run(["kubectl", "apply", "-f", manifest_path], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[✗] Failed to submit job:\n{result.stderr}")
        return

    print(f"[✓] Job submitted successfully! Tracking progress...")

    # 5. Poll the Kubernetes API for the Job status
    while True:
        status_cmd = ["kubectl", "get", "job", job_name, "-o", "json"]
        status_result = subprocess.run(status_cmd, capture_output=True, text=True)
        
        if status_result.returncode != 0:
            print(f"[!] Could not fetch status. The job might have been deleted.")
            break
            
        job_data = json.loads(status_result.stdout)
        conditions = job_data.get("status", {}).get("conditions", [])
        
        # Check for Complete or Failed status flags
        job_complete = any(c.get("type") == "Complete" and c.get("status") == "True" for c in conditions)
        job_failed = any(c.get("type") == "Failed" and c.get("status") == "True" for c in conditions)
        
        if job_complete:
            print(f"[✓] Video processing finished! Saved to host at: /home/doreen/ffmpeg-data/output/{output_filename}")
            break
        elif job_failed:
            print(f"[✗] Job '{job_name}' failed. Fetching pod logs...")
            log_result = subprocess.run(["kubectl", "logs", f"job/{job_name}"], capture_output=True, text=True)
            print(f"--- FFmpeg Logs ---\n{log_result.stdout}\n-------------------")
            break
            
        print("    Processing... (checking again in 5 seconds)")
        time.sleep(5)
        
    # 6. Clean up the local YAML file
    if os.path.exists(manifest_path):
        os.remove(manifest_path)
if __name__ == "__main__":
    # Example test execution
    prompt = "Compress this video for web streaming and lower the resolution to 720p"
    run_ffmpeg_job(prompt, "file_example_MP4_1920_18MG.mp4", "compressed_file_example_MP4_1920_18MG.mp4")