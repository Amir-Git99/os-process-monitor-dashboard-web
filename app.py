from flask import Flask, render_template_string, jsonify, request
import psutil
from datetime import datetime

app = Flask(__name__)

ADMIN_PIN = "1234"
CPU_THRESHOLD = 20.0
RAM_THRESHOLD = 300.0
action_logs = []

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OS Process Monitoring Dashboard</title>
  <style>
    body { font-family: 'Segoe UI', sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
    .stats { font-weight: bold; color: #a6e3a1; font-size: 1.1rem; }
    .controls { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; align-items: center; }
    input { padding: 8px 12px; border-radius: 6px; border: 1px solid #45475a; background: #313244; color: #fff; width: 260px; }
    button { padding: 8px 14px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }
    .btn-refresh { background: #89b4fa; color: #11111b; }
    .btn-kill { background: #f38ba8; color: #11111b; padding: 5px 10px; }
    table { width: 100%; border-collapse: collapse; background: #181825; border-radius: 8px; overflow: hidden; }
    th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #313244; }
    th { background: #11111b; color: #89b4fa; }
    tr.high-usage { background: #4a1c24; color: #ffb4b4; }
    .logs { margin-top: 20px; background: #11111b; padding: 12px; border-radius: 8px; font-family: monospace; font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class="header">
    <h2>System Process Monitoring & Management Dashboard</h2>
    <div class="stats" id="sysStats">Total CPU: 0% | Total RAM: 0%</div>
  </div>

  <div class="controls">
    <input type="text" id="searchBox" placeholder="Search process by name..." onkeyup="renderTable()" />
    <button class="btn-refresh" onclick="fetchProcesses()">Refresh Now</button>
    <span style="color:#f38ba8; margin-left:auto;">Alert Threshold: CPU &gt; {{ cpu_thresh }}% or RAM &gt; {{ ram_thresh }} MB</span>
  </div>

  <table>
    <thead>
      <tr>
        <th>PID</th>
        <th>Process Name</th>
        <th>Status</th>
        <th>CPU (%)</th>
        <th>Memory (MB)</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody id="processBody"></tbody>
  </table>

  <div class="logs">
    <strong>Termination Audit Log:</strong>
    <ul id="logList"><li>No processes terminated yet.</li></ul>
  </div>

  <script>
    let allProcesses = [];
    let adminPin = null;

    async function fetchProcesses() {
      try {
        const res = await fetch('/api/processes');
        const data = await res.json();
        document.getElementById('sysStats').innerText = `Total CPU: ${data.total_cpu}% | Total RAM: ${data.total_ram}%`;
        allProcesses = data.processes || [];
        renderTable();
        renderLogs(data.logs);
      } catch (err) {
        console.error(err);
      }
    }

    function renderTable() {
      const query = document.getElementById('searchBox').value.toLowerCase();
      const tbody = document.getElementById('processBody');
      tbody.innerHTML = '';

      allProcesses
        .filter(p => p.name.toLowerCase().includes(query))
        .forEach(p => {
          const row = document.createElement('tr');
          if (p.high_usage) row.classList.add('high-usage');
          row.innerHTML = `
            <td>${p.pid}</td>
            <td>${p.name}</td>
            <td>${p.status}</td>
            <td>${p.cpu}</td>
            <td>${p.memory}</td>
            <td><button class="btn-kill" onclick="killProcess(${p.pid}, '${p.name.replace(/'/g, "")}')">Terminate</button></td>
          `;
          tbody.appendChild(row);
        });
    }

    function renderLogs(logs) {
      const list = document.getElementById('logList');
      if (!logs || logs.length === 0) return;
      list.innerHTML = logs.map(l => `<li>${l}</li>`).join('');
    }

    async function killProcess(pid, name) {
      if (!adminPin) {
        adminPin = prompt("Enter Admin PIN (1234) to authorize termination:");
        if (!adminPin) return;
      }
      if (!confirm(`Are you sure you want to terminate '${name}' (PID: ${pid})?`)) return;

      const res = await fetch('/api/terminate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, pin: adminPin })
      });
      const result = await res.json();
      if (!res.ok) {
        adminPin = null;
        alert(result.message);
      } else {
        alert(result.message);
        fetchProcesses();
      }
    }

    fetchProcesses();
    setInterval(fetchProcesses, 3000);
  </script>
</body>
</html>
"""


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path):
    return render_template_string(HTML_TEMPLATE, cpu_thresh=CPU_THRESHOLD, ram_thresh=RAM_THRESHOLD)


@app.route("/api/processes")
def get_processes():
    try:
        total_cpu = psutil.cpu_percent(interval=None)
    except Exception:
        total_cpu = 0.0

    try:
        total_ram = psutil.virtual_memory().percent
    except Exception:
        total_ram = 0.0

    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_info']):
            try:
                info = proc.info
                cpu = info.get('cpu_percent') or 0.0
                mem_info = info.get('memory_info')
                mem_mb = round(mem_info.rss / (1024 * 1024), 2) if mem_info else 0.0
                processes.append({
                    "pid": info.get('pid', 0),
                    "name": info.get('name') or "Unknown",
                    "status": info.get('status') or "running",
                    "cpu": cpu,
                    "memory": mem_mb,
                    "high_usage": cpu > CPU_THRESHOLD or mem_mb > RAM_THRESHOLD
                })
            except Exception:
                pass
    except Exception:
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
    data = request.json or {}
    pin = data.get("pin")
    pid = int(data.get("pid", 0))

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
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
