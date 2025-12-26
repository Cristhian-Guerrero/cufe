"""
═══════════════════════════════════════════════════════════════════════════
SISTEMA DE LOGS - CUFE DIAN AUTOMATION
Sistema de logging con colores, timestamps y contextos
═══════════════════════════════════════════════════════════════════════════
"""

import threading
from datetime import datetime
from typing import Optional


class Logger:
    """
    Sistema de logging thread-safe con colores y contextos
    
    Soporta diferentes contextos:
    - Sistema (nav_id=0): [SYS]
    - Extractor (nav_id=99): [EXT]
    - Excel (nav_id=98): [XLS]
    - Navegadores (nav_id=1-N): [N1], [N2], etc.
    """
    
    # Colores ANSI
    COLORES = {
        "INFO": "\033[94m",    # Azul
        "OK": "\033[92m",      # Verde
        "WARN": "\033[93m",    # Amarillo
        "ERROR": "\033[91m",   # Rojo
        "DEBUG": "\033[96m",   # Cyan
        "CRIT": "\033[95m",    # Magenta
        "EXCEL": "\033[93m",   # Amarillo
        "RETRY": "\033[95m"    # Magenta
    }
    
    RESET = "\033[0m"
    
    def __init__(self, usar_colores=True):
        """
        Inicializa el logger
        
        Args:
            usar_colores: Si False, desactiva colores (útil para logs a archivo)
        """
        self._lock = threading.Lock()
        self._usar_colores = usar_colores
        self._archivo_log = None
    
    def configurar_archivo(self, ruta_archivo: str):
        """
        Configura logging a archivo (además de consola)
        
        Args:
            ruta_archivo: Ruta del archivo de log
        """
        try:
            self._archivo_log = open(ruta_archivo, 'a', encoding='utf-8')
        except Exception as e:
            print(f"⚠️  No se pudo abrir archivo de log: {e}")
    
    def _obtener_prefijo(self, nav_id: int) -> str:
        """
        Obtiene el prefijo según el contexto
        
        Args:
            nav_id: ID del navegador o contexto especial
            
        Returns:
            Prefijo formateado (ej: "[SYS]", "[N1]")
        """
        if nav_id == 0:
            return "[SYS]"
        elif nav_id == 99:
            return "[EXT]"
        elif nav_id == 98:
            return "[XLS]"
        else:
            return f"[N{nav_id}]"
    
    def log(self, nav_id: int, mensaje: str, nivel: str = "INFO"):
        """
        Registra un mensaje con timestamp, contexto y color
        
        Args:
            nav_id: ID del navegador o contexto (0=SYS, 99=EXT, 98=XLS, 1-N=navegador)
            mensaje: Mensaje a registrar
            nivel: Nivel de log (INFO, OK, WARN, ERROR, DEBUG, CRIT, EXCEL, RETRY)
        """
        with self._lock:
            # Timestamp con milisegundos
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Prefijo según contexto
            prefijo = self._obtener_prefijo(nav_id)
            
            # Construir mensaje
            if self._usar_colores:
                color = self.COLORES.get(nivel, "")
                linea = f"{color}{ts} {prefijo} [{nivel}] {mensaje}{self.RESET}"
            else:
                linea = f"{ts} {prefijo} [{nivel}] {mensaje}"
            
            # Imprimir a consola
            print(linea)
            
            # Guardar en archivo si está configurado
            if self._archivo_log:
                try:
                    # En archivo guardamos sin colores
                    linea_archivo = f"{ts} {prefijo} [{nivel}] {mensaje}\n"
                    self._archivo_log.write(linea_archivo)
                    self._archivo_log.flush()
                except:
                    pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # MÉTODOS DE CONVENIENCIA
    # ═══════════════════════════════════════════════════════════════════════
    
    def info(self, nav_id: int, mensaje: str):
        """Log de información"""
        self.log(nav_id, mensaje, "INFO")
    
    def ok(self, nav_id: int, mensaje: str):
        """Log de éxito"""
        self.log(nav_id, mensaje, "OK")
    
    def warn(self, nav_id: int, mensaje: str):
        """Log de advertencia"""
        self.log(nav_id, mensaje, "WARN")
    
    def error(self, nav_id: int, mensaje: str):
        """Log de error"""
        self.log(nav_id, mensaje, "ERROR")
    
    def debug(self, nav_id: int, mensaje: str):
        """Log de debug"""
        self.log(nav_id, mensaje, "DEBUG")
    
    def critico(self, nav_id: int, mensaje: str):
        """Log crítico"""
        self.log(nav_id, mensaje, "CRIT")
    
    def excel(self, nav_id: int, mensaje: str):
        """Log relacionado a Excel"""
        self.log(nav_id, mensaje, "EXCEL")
    
    def retry(self, nav_id: int, mensaje: str):
        """Log de reintento"""
        self.log(nav_id, mensaje, "RETRY")
    
    def cerrar(self):
        """Cierra el archivo de log si está abierto"""
        if self._archivo_log:
            try:
                self._archivo_log.close()
            except:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# INSTANCIA GLOBAL (opcional, para facilitar imports)
# ═══════════════════════════════════════════════════════════════════════════

# Instancia global por defecto
_logger_global = Logger()


def log(nav_id: int, mensaje: str, nivel: str = "INFO"):
    """
    Función global de logging (compatibilidad con código original)
    
    Args:
        nav_id: ID del navegador o contexto
        mensaje: Mensaje a registrar
        nivel: Nivel de log
    """
    _logger_global.log(nav_id, mensaje, nivel)


def obtener_logger() -> Logger:
    """Obtiene la instancia global del logger"""
    return _logger_global


def crear_logger(usar_colores: bool = True, archivo_log: Optional[str] = None) -> Logger:
    """
    Crea una nueva instancia de Logger
    
    Args:
        usar_colores: Activar colores en consola
        archivo_log: Ruta opcional del archivo de log
        
    Returns:
        Nueva instancia de Logger
    """
    logger = Logger(usar_colores=usar_colores)
    if archivo_log:
        logger.configurar_archivo(archivo_log)
    return logger


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 PROBANDO SISTEMA DE LOGS")
    print("="*70 + "\n")
    
    # Crear logger
    logger = crear_logger()
    
    # Probar diferentes contextos
    logger.info(0, "Sistema iniciado")
    logger.ok(1, "Navegador 1 conectado")
    logger.warn(2, "Navegador 2 con delay")
    logger.error(3, "Navegador 3 falló descarga")
    logger.debug(99, "Extrayendo datos del PDF")
    logger.excel(98, "Generando Excel...")
    logger.retry(5, "Reintentando CUFE #123")
    logger.critico(0, "Error crítico del sistema")
    
    print("\n" + "="*70)
    print("✅ Test de logs completado")
    print("="*70 + "\n")
