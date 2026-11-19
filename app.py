from flask import Flask, render_template, jsonify, request
import psutil
from datetime import datetime

app = Flask(__name__)

ADMIN_PIN = "1234"
CPU_THRESHOLD = 20.0
RAM_THRESHOLD = 300.0
action_logs = []  # In-memory audit log (Vercel's filesystem is read-only)


@app.route("/")
def index():
    return render_template("index.html", cpu_thresh=CPU_THRESHOLD, ram_thresh=RAM_THRESHOLD)


@app.route("/api/processes")
def get_processes():
    total_cpu = psutil.cpu_percent(interval=None)
    total_ram = psutil.virtual_memory().percent
    processes = []

    for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_info']):
        try:
            info = proc.info
            cpu = info['cpu_percent'] or 0.0
            mem_mb = round(info['memory_info'].rss / (1024 * 1024), 2) if info['memory_info'] else 0.0
            processes.append({
                "pid": info['pid'],
                "name": info['name'] or "Unknown",
                "status": info['status'],
                "cpu": cpu,
                "memory": mem_mb,
                "high_usage": cpu > CPU_THRESHOLD or mem_mb > RAM_THRESHOLD
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    processes.sort(key=lambda x: x["cpu"], reverse=True)
    return jsonify({
        "total_cpu": total_cpu,
        "total_ram": total_ram,
        "processes": processes,
        "logs": action_logs
    })


@app.route("/api/terminate", methods=["POST"])
def terminate_process():
    data = request.json
    pin = data.get("pin")
    pid = int(data.get("pid"))

    if pin != ADMIN_PIN:
        return jsonify({"success": False, "message": "Invalid Admin PIN! Access Denied."}), 403

    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        proc.wait(timeout=3)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        action_logs.insert(0, f"[{timestamp}] TERMINATED | PID: {pid} | Process: {name}")
        return jsonify({"success": True, "message": f"Process '{name}' (PID: {pid}) terminated."})
    except psutil.TimeoutExpired:
        proc.kill()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        action_logs.insert(0, f"[{timestamp}] FORCE KILLED | PID: {pid} | Process: {name}")
        return jsonify({"success": True, "message": f"Process '{name}' (PID: {pid}) force-killed."})
    except psutil.AccessDenied:
        return jsonify({"success": False, "message": "OS Access Denied! Cannot terminate protected system process."}), 403
    except psutil.NoSuchProcess:
        return jsonify({"success": False, "message": "Process already ended."}), 404


if __name__ == "__main__":
    app.run(debug=True)