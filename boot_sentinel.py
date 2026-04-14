import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    print("[!] psutil no encontrado. Ejecuta: pip install psutil")
    sys.exit(1)

# ==========================================
# CONFIGURACION DEL SENTINEL
# ==========================================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"boot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("Sentinel")

PORTS_TO_CLEAR = {
    8000: "FastAPI Backend",
    3000: "Next.js Frontend",
}


class BootSentinel:
    def __init__(self):
        self.processes = []
        logger.info("=== INICIANDO SECUENCIA SENTINEL 2024 ===")

    def sweep_zombies(self):
        """Escanea y aniquila cualquier proceso que ocupe nuestros puertos vitales."""
        logger.info(">> FASE 1: BARRIENDO PROCESOS ZOMBIE...")

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                for conn in proc.net_connections(kind="inet"):
                    if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port in PORTS_TO_CLEAR:
                        port = conn.laddr.port
                        service = PORTS_TO_CLEAR[port]
                        logger.warning(
                            f"[!] Zombie detectado: PID {proc.info['pid']} ({proc.info['name']}) "
                            f"bloqueando el puerto {port} ({service})."
                        )

                        p = psutil.Process(proc.info["pid"])
                        p.terminate()
                        p.wait(timeout=3)
                        logger.info(f"[+] Proceso PID {proc.info['pid']} aniquilado y puerto {port} liberado.")
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except psutil.TimeoutExpired:
                logger.warning(
                    f"[!] PID {proc.info.get('pid')} no respondio a terminate(). Intentando kill forzado."
                )
                try:
                    p = psutil.Process(proc.info["pid"])
                    p.kill()
                    p.wait(timeout=3)
                    logger.info(f"[+] Proceso PID {proc.info['pid']} eliminado por kill forzado.")
                except Exception:
                    pass

        logger.info("[OK] Puertos limpios.")

    def is_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def start_docker_infrastructure(self):
        """Inicia PostgreSQL y Redis via Docker Compose."""
        logger.info(">> FASE 2: VERIFICANDO INFRAESTRUCTURA CORE (DOCKER)...")
        if not self.is_port_in_use(5454):
            logger.info("[*] Levantando base de datos y cache...")
            subprocess.Popen(
                ["docker-compose", "up", "-d"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(5)
            if not self.is_port_in_use(5454):
                logger.error("[FATAL] Docker no pudo exponer PostgreSQL en el puerto 5454.")
                sys.exit(1)
        logger.info("[OK] Infraestructura Core lista.")

    def start_backend(self):
        """Levanta FastAPI."""
        logger.info(">> FASE 3: INICIANDO MOTOR BACKEND...")

        if os.name == "nt":
            python_executable = os.path.join("backend", "venv", "Scripts", "python.exe")
        else:
            python_executable = os.path.join("backend", "venv", "bin", "python")

        if not os.path.exists(python_executable):
            python_executable = "python"

        backend_cmd = [python_executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"]
        backend_proc = subprocess.Popen(backend_cmd, cwd="backend")
        self.processes.append(backend_proc)

        retries = 10
        while retries > 0 and not self.is_port_in_use(8000):
            time.sleep(1)
            retries -= 1

        if retries == 0:
            logger.error("[FATAL] Backend fallo en el arranque.")
            self.shutdown()
            sys.exit(1)
        logger.info("[OK] API Backend operativa en puerto 8000.")

    def start_frontend(self):
        """Levanta Next.js."""
        logger.info(">> FASE 4: INICIANDO COMMAND CENTER (FRONTEND)...")
        shell_flag = os.name == "nt"
        frontend_proc = subprocess.Popen(["npm", "run", "dev"], cwd="frontend", shell=shell_flag)
        self.processes.append(frontend_proc)

        retries = 15
        while retries > 0 and not self.is_port_in_use(3000):
            time.sleep(1)
            retries -= 1

        if retries == 0:
            logger.error("[FATAL] Frontend fallo en el arranque.")
            self.shutdown()
            sys.exit(1)
        logger.info("[OK] Frontend UI operativo en puerto 3000.")

    def run(self):
        try:
            self.sweep_zombies()
            self.start_docker_infrastructure()
            self.start_backend()
            self.start_frontend()

            logger.info("=============================================")
            logger.info("SISTEMA TOTALMENTE EN LINEA Y AUDITADO")
            logger.info("Frontend: http://localhost:3000")
            logger.info("Backend:  http://localhost:8000/docs")
            logger.info("=============================================")
            logger.info("Presiona Ctrl+C para apagar todo de forma segura.")

            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("\n[*] Senal de apagado recibida. Iniciando protocolo de cierre limpio...")
            self.shutdown()

    def shutdown(self):
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        logger.info("[OK] Todos los subprocesos han sido terminados.")
        logger.info("=== SECUENCIA TERMINADA ===")


if __name__ == "__main__":
    sentinel = BootSentinel()
    sentinel.run()
