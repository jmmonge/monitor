import os
import subprocess
import glob
import webbrowser
import re
import ssl
import imaplib
import email
import json
from datetime import datetime

# ================= CONFIGURACIÓN =================
OUTPUT_FILE = "Estado_GMU.html"
RUTA_JSON = os.path.join(os.path.dirname(__file__), "ficheros_json")
ESTADO_EMAIL_FILE = os.path.join(RUTA_JSON, "estado_hbs3.json")
VEEAM_JSON_FILE = os.path.join(RUTA_JSON, "veeam_status.json")

# Configuración NUXIT
NUXIT_IP = "195.144.11.125"
NUXIT_PORT = "25245"
NUXIT_USER = "p5245"

# Configuración IMAP (Hybrid Backup Sync)
IMAP_SERVER = "91.191.159.139"
IMAP_PORT = 993
IMAP_USER = "qnap@gmusanlucar.es"
IMAP_PASS = "1correogmu"

# Tiempos de espera (Segundos)
TIMEOUT_GENERAL = 10 


# Servidores para Ping
servidores = [
    ("ServerNuevo", "192.168.20.254"),
    ("GMU00", "192.168.20.200"),
    ("Mi Ubuntu", "192.168.20.208"),
    ("Portal Emp.", "192.168.20.210"),
    ("GMU01", "192.168.20.201"),
    ("NAS", "192.168.20.206"),
    ("GMU03", "192.168.20.202")
]

# Rutas Backups Locales
rutas_backups = [
    ("Archivo", r"\\nas\respaldo\Ubuntu\archivo*"),
    ("Urbe", r"\\nas\respaldo\Ubuntu\urbe*"),
    ("Decretos", r"\\nas\respaldo\Ubuntu\decretos*"),
    ("Vivienda", r"\\nas\respaldo\Ubuntu\vivienda*"),
    ("Secretaria", r"\\nas\respaldo\Ubuntu\secretaria*"),
    ("Inventario", r"\\nas\respaldo\Ubuntu\inventario*"),
    ("RD", r"\\nas\respaldo\Ubuntu\rd*"),
    ("Portal Emp.", r"\\nas\respaldo\PortalEmpleado\Empleados*")
]

tareas_hbs3 = [
    'Sincronizar "De Ubuntu a Synology"',
    'Sincronizar "Raid a Synology"',
    'Sincronizar "Sincronizar ficheros Urbe"'
]

# ================= UTILIDADES =================

def formatear_fecha_veeam(fecha_str):
    if not fecha_str or "Sin datos" in str(fecha_str): return "-"
    try:
        if "/Date" in str(fecha_str):
            ms = int(re.search(r'\d+', str(fecha_str)).group())
            return datetime.fromtimestamp(ms / 1000.0).strftime("%d/%m/%Y %H:%M")
        return datetime.fromisoformat(str(fecha_str).replace('Z', '+00:00')).strftime("%d/%m/%Y %H:%M")
    except: return str(fecha_str)

def run_ssh(host, port, user, command):
    print(f"--> [SSH] {host}...")
    #cmd = f'ssh -o ConnectTimeout=5 -p {port} {user}@{host} "{command}"'
    cmd = f'ssh -o ConnectTimeout={TIMEOUT_GENERAL} -p {port} {user}@{host} "{command}"'
    try:
        #r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=TIMEOUT_GENERAL + 2)
        return r.stdout.strip() if r.stdout else ""
    except: return ""

def check_ping(ip):
    param = "-n" if os.name == "nt" else "-c"
    return subprocess.run(["ping", param, "1", "-w", "800", ip], stdout=subprocess.DEVNULL).returncode == 0

def check_monitor_descargas():
    comando = "pgrep -af 'tail -n0 -F /home/logs/gmusanlucar.es.log'"
    salida = run_ssh(NUXIT_IP, NUXIT_PORT, NUXIT_USER, comando)
    return bool(salida)

def get_backup_info(nombre, ruta):
    files = glob.glob(ruta)
    if not files:
        return f'<tr><td>{nombre}</td><td><span class="badge badge-red">ERROR</span></td><td>-</td><td>-</td></tr>'
    ultimo = max(files, key=os.path.getmtime)
    mtime = datetime.fromtimestamp(os.path.getmtime(ultimo))
    size = f"{os.path.getsize(ultimo)/1024:,.2f} KB"
    cls = "badge-green" if (datetime.now() - mtime).days <= 1 else "badge-orange"
    return f'<tr><td>{nombre}</td><td><span class="badge {cls}">OK</span></td><td>{mtime.strftime("%d/%m/%Y %H:%M")}</td><td>{size}</td></tr>'

if os.path.exists(VEEAM_JSON_FILE):
    try:
        os.remove(VEEAM_JSON_FILE)
    except: pass
    
# ================= EJECUCIÓN PREVIA DE VEEAM =================
print("--> 🌀 Ejecutando script de Veeam (PowerShell)...")
try:
    ps_path = os.path.join(os.path.dirname(__file__), "veeam.ps1")
    subprocess.run(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps_path], 
                   timeout=60, check=False) # Timeout largo para PS
    print("    [OK] Script de Veeam finalizado.")
except subprocess.TimeoutExpired:
    print("    [!] El script de PowerShell tardó demasiado.")

# A partir de aquí continúa el resto de tu script...
print(f"\n🚀 INICIANDO RECOLECCIÓN - {datetime.now().strftime('%H:%M:%S')}")


# ================= RECOLECCIÓN =================
now = datetime.now()
print(f"🚀 Procesando GMU Dashboard - {now.strftime('%H:%M:%S')}")

# 1. Qnap IMAP
if os.path.exists(ESTADO_EMAIL_FILE):
    with open(ESTADO_EMAIL_FILE, "r", encoding="utf-8-sig") as f:
        try: estado_qnap = json.load(f)
        except: estado_qnap = {}
else: estado_qnap = {}

try:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, ssl_context=ssl_ctx)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select("INBOX")
    _, data = mail.search(None, 'ALL')
    for num in data[0].split():
        _, msg_data = mail.fetch(num, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        f_mail = email.utils.parsedate_to_datetime(msg["Date"])
        cuerpo = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    cuerpo += part.get_payload(decode=True).decode(errors="replace")
        else: cuerpo = msg.get_payload(decode=True).decode(errors="replace")
        
        cuerpo = cuerpo.replace("\n", " ").replace("\r", " ")
        for t in tareas_hbs3:
            if t in cuerpo and "ha finalizado" in cuerpo:
                estado_qnap[t] = {"fecha": f_mail.strftime("%Y-%m-%d %H:%M:%S")}
        mail.store(num, '+FLAGS', '\\Deleted')
    mail.expunge()
    mail.logout()
except: pass

with open(ESTADO_EMAIL_FILE, "w", encoding="utf-8") as f: json.dump(estado_qnap, f, indent=4)

# 2. Veeam
html_veeam = ""
if os.path.exists(VEEAM_JSON_FILE):
    with open(VEEAM_JSON_FILE, "r", encoding="utf-8-sig") as f:
        try:
            v_data = json.load(f)
            if isinstance(v_data, dict): v_data = [v_data]
            for j in v_data:
                res = j.get("LastResult", "N/A")
                f_v = formatear_fecha_veeam(j.get('LastRun'))
                cls = "badge-green" if res == "Success" else "badge-red"
                html_veeam += f"<tr><td>{j.get('Trabajo')}</td><td>{j.get('Tipo')}</td><td><span class='badge {cls}'>{res}</span></td><td>{f_v}</td></tr>"
        except Exception as e: html_veeam = f"<tr><td colspan='4'>Error: {e}</td></tr>"

# 3. Pings e Indicadores
html_srv = ""
for n, ip in servidores:
    up = check_ping(ip)
    col = "#10b981" if up else "#ef4444"
    html_srv += f'<div class="card"><div class="status-indicator" style="background:{col}"></div><div class="card-body"><strong>{n}</strong><br><small>{ip}</small><br><span style="color:{col}; font-weight:bold; font-size:13px;">{"ONLINE" if up else "OFFLINE"}</span></div></div>'

# 2. Añadir el Monitor de Descargas de NUXIT (fuera del bucle)
# Usamos la función check_monitor_descargas() que ya tienes definida
monitor_up = check_monitor_descargas() 
col_mon = "#10b981" if monitor_up else "#ef4444"
html_srv += f'<div class="card"><div class="status-indicator" style="background:{col_mon}"></div><div class="card-body"><strong>Monitor Descargas</strong><br><small>NUXIT</small><br><span style="color:{col_mon}; font-weight:bold; font-size:13px;">{"ON" if monitor_up else "OFF"}</span></div></div>'


# 4. Logs SSH
nuxit_logs = run_ssh(NUXIT_IP, NUXIT_PORT, NUXIT_USER, "tail -n 6 /home/www/gmu10/mis_scripts/logs/log_drupal.txt").replace("\n", "<br>")
nuxit_ip = run_ssh(NUXIT_IP, NUXIT_PORT, NUXIT_USER, "tail -n 6 /home/www/transparencia/web/.htaccess").replace("\n", "<br>")

def get_u(ip):
    r = run_ssh(ip, "22", "jmmonge", "who -b && echo '---' && apt list --upgradable 2>/dev/null | grep /")
    if not r: return '<span class="badge">Error</span>', "No disponible"
    p = r.split('---')
    u = [l for l in p[1].split('\n') if "/" in l] if len(p)>1 else []
    b = f'<span class="badge badge-red">{len(u)} updates</span>' if u else '<span class="badge badge-green">Actualizado</span>'
    return b, r.replace("\n", "<br>")

b208, t208 = get_u("192.168.20.208")
b210, t210 = get_u("192.168.20.210")

# MONITOR DE DESCARGAS EN NUXIT
monitor_activo = check_monitor_descargas()
color_monitor = "#10b981" if monitor_activo else "#ef4444"
estado_monitor = "ON" if monitor_activo else "OFF"



# ================= CONSTRUCCIÓN HTML =================

html_qnap_rows = ""
for t in tareas_hbs3:
    inf = estado_qnap.get(t)
    badge, f_str = ('<span class="badge badge-red">SIN DATOS</span>', "-")
    if inf:
        f_dt = datetime.strptime(inf["fecha"], "%Y-%m-%d %H:%M:%S")
        c = "badge-green" if (now - f_dt).days <= 1 else "badge-orange"
        badge, f_str = (f'<span class="badge {c}">OK</span>', f_dt.strftime("%d/%m/%Y %H:%M"))
    html_qnap_rows += f"<tr><td>{t}</td><td>{badge}</td><td>{f_str}</td></tr>"

html_final = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Monitorización Sistemas GMU</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #f8fafc; color: #334155; margin: 0; padding: 20px; }}
        .container {{ width: 80%; margin: 0 auto; }}
        h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .timestamp {{ font-size: 13px; color: #64748b; margin-bottom: 25px; display: block; }}
        
        /* Servidores centrados */
        .grid-servers {{ display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; margin-bottom: 30px; }}
        .card {{ background: white; padding: 12px; border-radius: 4px; min-width: 140px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
        .status-indicator {{ height: 4px; margin: -12px -12px 10px -12px; border-radius: 4px 4px 0 0; }}
        
        /* Tablas y Secciones */
        h3 {{ background: wheat; padding: 5px; border-left: 4px solid #f59e0b; font-size: 1.17em; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 10px; margin-top: -12px;table-layout: fixed; }}
        th, td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: center; }}
        th {{ background: #E2E8F0; font-weight: 600; text-align: center; font-size: 14px; }}
        
        /* Layout columnas */
        .flex-row {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .flex-col {{ flex: 1; }}

        /* Consolas */
        .console {{ background: #0f172a; color: #d1fae5; padding: 15px; border-radius: 6px; font-family: 'Consolas', monospace; font-size: 14px; min-height: 80px; margin-bottom: 10px; overflow-x: auto; 20px; }}
        .badge {{ padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
        .badge-green {{ background: #d1fae5; color: #065f46; }}
        .badge-red {{ background: #fee2e2; color: #991b1b; }}
        .badge-orange {{ background: #ffedd5; color: #9a3412; }}
        h4 {{ margin-bottom: 8px; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ Monitorización Sistemas GMU</h1>
        <span class="timestamp">Generado: {now.strftime("%d/%m/%Y %H:%M:%S")}</span>

        <h3>🌐 Estado de Servidores</h3>
        <div class="grid-servers">{html_srv}</div>

        <div class="flex-row">
            <div class="flex-col">
                <h3>☁️ Copias Qnap a Synology (HBS3)</h3>
                <table><thead><tr><th>Tarea</th><th>Estado</th><th>Último correo</th></tr></thead><tbody>{html_qnap_rows}</tbody></table>
                
                <h3>💾 Backups Veeam (ServerNuevo)</h3>
                <table><thead><tr><th>Trabajo</th><th>Tipo</th><th>Resultado</th><th>Finalizado</th></tr></thead><tbody>{html_veeam}</tbody></table>
            </div>
            <div class="flex-col">
                <h3>📂 Backups en Synology (Locales)</h3>
                <table><thead><tr><th>Recurso</th><th>Estado</th><th>Última modif.</th><th>Tamaño</th></tr></thead>
                <tbody>{''.join(get_backup_info(n, r) for n, r in rutas_backups)}</tbody></table>
            </div>
        </div>

        <h3>📡 NUXIT</h3>
        <div class="flex-row">
            <div class="flex-col"><h4>Logs lecturas archivos compartidos</h4><div class="console">{nuxit_logs}</div></div>
            <div class="flex-col"><h4>Bloqueos IP transparencia</h4><div class="console" style="color:#93c5fd">{nuxit_ip}</div></div>
        </div>

        <h3>🐧 Servidores Ubuntu</h3>
        <div class="flex-row">
            <div class="flex-col"><h4>Mi Ubuntu .208 {b208}</h4><div class="console">{t208}</div></div>
            <div class="flex-col"><h4>Portal Emp .210 {b210}</h4><div class="console">{t210}</div></div>
        </div>
    </div>
</body>
</html>
"""

with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write(html_final)
webbrowser.open("file://" + os.path.realpath(OUTPUT_FILE))
print("✅ Informe generado correctamente al 80% de ancho.")