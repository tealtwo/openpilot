#!/usr/bin/env python3
"""
Lightweight web server for clip.py
Runs on port 8084
"""
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for

app = Flask(__name__)

# Configuration
OPENPILOT_DIR = Path(__file__).parent.parent.parent.resolve()
JOBS_FILE = OPENPILOT_DIR / 'tools' / 'clip' / 'jobs.json'
OUTPUT_DIR = OPENPILOT_DIR / 'tools' / 'clip' / 'outputs'
OUTPUT_DIR.mkdir(exist_ok=True)

# Job storage
def load_jobs():
    if JOBS_FILE.exists():
        with open(JOBS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_jobs(jobs):
    with open(JOBS_FILE, 'w') as f:
        json.dump(jobs, f, indent=2)

jobs = load_jobs()
jobs_lock = threading.Lock()

def run_clip_job(job_id, route, start, end, quality, filesize):
    """Run clip.py in background"""
    with jobs_lock:
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['started_at'] = datetime.now().isoformat()
        save_jobs(jobs)

    output_file = OUTPUT_DIR / f"{job_id}.mp4"

    try:
        cmd = [
            'python', str(OPENPILOT_DIR / 'tools' / 'clip' / 'run.py'),
            f'{route}/{start}/{end}',
            '-q', quality,
            '-f', str(filesize),
            '-o', str(output_file)
        ]

        result = subprocess.run(
            cmd,
            cwd=OPENPILOT_DIR,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )

        with jobs_lock:
            if result.returncode == 0:
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['output_file'] = str(output_file)
                jobs[job_id]['file_size'] = output_file.stat().st_size
            else:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['error'] = result.stderr[-500:]  # Last 500 chars
            jobs[job_id]['completed_at'] = datetime.now().isoformat()
            save_jobs(jobs)

    except subprocess.TimeoutExpired:
        with jobs_lock:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = 'Job timed out after 30 minutes'
            save_jobs(jobs)
    except Exception as e:
        with jobs_lock:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
            save_jobs(jobs)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    with jobs_lock:
        return jsonify(jobs)

@app.route('/api/submit', methods=['POST'])
def submit_job():
    data = request.json
    route = data.get('route')
    start = data.get('start')
    end = data.get('end')
    quality = data.get('quality', 'high')
    filesize = data.get('filesize', 50)

    # Validate inputs
    if not route or start is None or end is None:
        return jsonify({'error': 'Missing required fields'}), 400

    # Generate job ID
    job_id = f"clip_{int(time.time())}_{route.replace('/', '_')}"

    # Create job entry
    with jobs_lock:
        jobs[job_id] = {
            'id': job_id,
            'route': route,
            'start': start,
            'end': end,
            'quality': quality,
            'filesize': filesize,
            'status': 'queued',
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
            'output_file': None,
            'error': None
        }
        save_jobs(jobs)

    # Start job in background thread
    thread = threading.Thread(
        target=run_clip_job,
        args=(job_id, route, start, end, quality, filesize)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id, 'message': 'Job started'})

@app.route('/api/download/<job_id>')
def download_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job['status'] != 'completed':
            return jsonify({'error': 'Job not found or not completed'}), 404

        output_file = Path(job['output_file'])
        if not output_file.exists():
            return jsonify({'error': 'Output file not found'}), 404

        return send_file(output_file, as_attachment=True, download_name=f"{job_id}.mp4")

@app.route('/api/delete/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        # Delete output file if exists
        if job.get('output_file'):
            output_file = Path(job['output_file'])
            if output_file.exists():
                output_file.unlink()

        # Remove from jobs
        del jobs[job_id]
        save_jobs(jobs)

        return jsonify({'message': 'Job deleted'})

@app.route('/api/rebuild', methods=['POST'])
def rebuild():
    """Git pull and rebuild openpilot"""
    def run_rebuild():
        try:
            # Git pull
            result = subprocess.run(
                ['git', 'pull'],
                cwd=OPENPILOT_DIR,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"Git pull failed: {result.stderr}")
                return

            # Rebuild
            result = subprocess.run(
                ['scons', f'-j{os.cpu_count()}'],
                cwd=OPENPILOT_DIR,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                print(f"Build failed: {result.stderr}")
            else:
                print("Rebuild completed successfully")

        except Exception as e:
            print(f"Rebuild error: {e}")

    # Run in background
    thread = threading.Thread(target=run_rebuild)
    thread.daemon = True
    thread.start()

    return jsonify({'message': 'Rebuild started in background'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8084, debug=False)
