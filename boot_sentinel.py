import logging
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
import atexit
from urllib.error import URLError
from urllib.request import urlopen

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
        self.processes = {}
        self._shutdown_called = False
        atexit.register(self.shutdown)
        signal.signal(signal.SIGINT, self._handle_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, self._handle_signal)
        logger.info("=== INICIANDO SECUENCIA SENTINEL 2024 ===")

    def _handle_signal(self, signum, _frame):
        logger.info(f"\n[*] Senal {signum} recibida. Iniciando protocolo de cierre limpio...")
        self.shutdown()
        raise SystemExit(0)

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

    def wait_http_ready(self, url, retries, process=None):
        """
        Espera una respuesta HTTP valida.
        Si el proceso muere antes de responder, falla inmediatamente.
        """
        while retries > 0:
            if process is not None and process.poll() is not None:
                return False
            try:
                with urlopen(url, timeout=1.5) as response:
                    if 200 <= response.status < 500:
                        return True
            except URLError:
                pass
            except Exception:
                pass
            time.sleep(1)
            retries -= 1
        return False

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

        backend_cmd = [
            python_executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            "8000",
            "--http",
            "h11",
        ]
        backend_proc = subprocess.Popen(backend_cmd, cwd="backend")
        self.processes["backend"] = backend_proc

        # Validacion fuerte: puerto abierto + endpoint real respondiendo.
        retries = 15
        while retries > 0 and not self.is_port_in_use(8000):
            if backend_proc.poll() is not None:
                break
            time.sleep(1)
            retries -= 1

        backend_ok = retries > 0 and self.wait_http_ready(
            "http://127.0.0.1:8000/api/health", retries=12, process=backend_proc
        )
        if not backend_ok:
            logger.error("[FATAL] Backend fallo en el arranque.")
            self.shutdown()
            sys.exit(1)
        logger.info("[OK] API Backend operativa en puerto 8000 (health check validado).")

    def start_frontend(self):
        logger.info(">> FASE 4: INICIANDO COMMAND CENTER (FRONTEND)...")
        frontend_dir = os.path.join(os.getcwd(), 'frontend')
        
        env_mode = os.environ.get("COMMAND_CENTER_ENV", "dev")
        
        if env_mode == "prod":
            logger.info(">>> MODO PRODUCCIÓN DETECTADO. Iniciando compilación (Build)...")
            logger.info(">>> Esto puede tardar unos minutos la primera vez. Por favor espera...")
            # 1. Compilar
            build_process = subprocess.Popen(
                ["npm", "run", "build"],
                cwd=frontend_dir,
                shell=True
            )
            build_process.wait()
            
            if build_process.returncode != 0:
                logger.error("Error crítico durante la compilación del Frontend. Abortando.")
                return
                
            logger.info(">>> Compilación exitosa. Iniciando servidor de producción...")
            # 2. Iniciar Producción
            self.processes['frontend'] = subprocess.Popen(
                ["npm", "start"],
                cwd=frontend_dir,
                shell=True
            )
        else:
            logger.info(">>> MODO DESARROLLO DETECTADO.")
            # Modo Dev normal
            self.processes['frontend'] = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=frontend_dir,
                shell=True
            )

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
        if self._shutdown_called:
            return
        self._shutdown_called = True
        for proc in self.processes.values():
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
