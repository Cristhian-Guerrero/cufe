"""
═══════════════════════════════════════════════════════════════════════════
DESCARGADOR - CUFE DIAN AUTOMATION
v3.8.0 - Nuevo flujo portal DIAN (campo NIT + popup + bloqueo anti-robot)
═══════════════════════════════════════════════════════════════════════════

CAMBIOS v3.8.0 (adaptación portal DIAN 2026-07-28):
1. descargar_cufe() recibe parámetro 'nit' — obligatorio para búsqueda
2. Flujo: CUFE → esperar campo NIT → ingresar NIT → buscar
3. Popup "Aceptar" detectado y clicado automáticamente tras solicitar descarga
4. Detección de "Solicitud bloqueada" → estado 'bloqueado_robot'
5. _buscar_campo_nit(): múltiples selectores CSS con fallback
6. _detectar_bloqueo_robot(): verifica texto del bloqueo de seguridad DIAN

CAMBIOS v3.7.1:
1. _limpiar_locks_perfil(): elimina SingletonLock/Socket/Cookie huérfanos
2. _liberar_puerto_chrome(): mata procesos Chrome/Edge zombi en el puerto CDP
"""

import time
import os
import csv
import hashlib
import threading
import json
import shutil
import tempfile
import platform
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions
from utils import log

# === VARIABLES GLOBALES DEL MÓDULO ===
lock_mapping = threading.Lock()
lock_navegadores = threading.Lock()
mapping_cufes = {}
navegadores_activos = {}  # Cambiado a dict: {nav_id: page}
ARCHIVO_MAPPING = "mapping_cufes_pdfs.json"

# Carpeta base para datos de Chrome (configurable)
_carpeta_chrome_base = None

# Perfil persistente: None = auto (True en Windows, False en Linux).
# Se puede sobreescribir con configurar_perfil_persistente() antes de inicializar.
_perfil_persistente = None

# === TELEMETRÍA ===
_archivo_metricas = None
_lock_metricas = threading.Lock()


def configurar_carpeta_chrome(carpeta_temp: str):
    """Configura la carpeta base para los datos de Chrome"""
    global _carpeta_chrome_base
    _carpeta_chrome_base = carpeta_temp
    os.makedirs(_carpeta_chrome_base, exist_ok=True)


def obtener_carpeta_chrome(nav_id: int) -> str:
    """Obtiene la carpeta de datos para un navegador específico"""
    global _carpeta_chrome_base
    
    if _carpeta_chrome_base is None:
        # Usar carpeta temporal del sistema por defecto
        _carpeta_chrome_base = os.path.join(tempfile.gettempdir(), "cufe_dian_chrome")
        os.makedirs(_carpeta_chrome_base, exist_ok=True)
    
    return os.path.join(_carpeta_chrome_base, f"chrome_{nav_id}")


def limpiar_carpetas_chrome():
    """Elimina TODAS las carpetas de datos de Chrome creadas"""
    global _carpeta_chrome_base
    
    carpetas_a_limpiar = []
    
    # 1. Carpeta base configurada
    if _carpeta_chrome_base and os.path.exists(_carpeta_chrome_base):
        carpetas_a_limpiar.append(_carpeta_chrome_base)
    
    # 2. Carpetas en directorio actual (legacy)
    cwd = os.getcwd()
    try:
        for item in os.listdir(cwd):
            if item.startswith('.chrome_dian_') or item.startswith('chrome_'):
                ruta = os.path.join(cwd, item)
                if os.path.isdir(ruta):
                    carpetas_a_limpiar.append(ruta)
    except:
        pass
    
    # 3. Carpetas en temp del sistema
    temp_dir = tempfile.gettempdir()
    try:
        for item in os.listdir(temp_dir):
            if item.startswith('cufe_dian_chrome'):
                ruta = os.path.join(temp_dir, item)
                if os.path.isdir(ruta):
                    carpetas_a_limpiar.append(ruta)
    except:
        pass
    
    # Eliminar todas
    eliminadas = 0
    for carpeta in carpetas_a_limpiar:
        try:
            shutil.rmtree(carpeta, ignore_errors=True)
            eliminadas += 1
        except:
            pass
    
    if eliminadas > 0:
        log(0, f"🧹 {eliminadas} carpetas Chrome eliminadas", "INFO")
    
    return eliminadas


def guardar_mapping():
    """Guarda mapping JSON de forma segura"""
    with lock_mapping:
        try:
            with open(ARCHIVO_MAPPING, 'w', encoding='utf-8') as f:
                json.dump(mapping_cufes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando mapping: {e}")


def _esperar(condicion, timeout: float = 3.0, intervalo: float = 0.05) -> bool:
    """
    Espera activa: evalúa condicion() repetidamente hasta que sea True
    o se agote el timeout. Reemplaza time.sleep() fijo por espera inteligente.

    Args:
        condicion : callable sin argumentos que devuelve bool
        timeout   : máximo de segundos a esperar (default 3s)
        intervalo : segundos entre cada evaluación (default 50ms)

    Returns:
        True si la condición se cumplió, False si se agotó el timeout
    """
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            if condicion():
                return True
        except Exception:
            pass
        time.sleep(intervalo)
    return False


def generar_nombre_unico(cufe: str, nav_id: int) -> str:
    """Genera nombre único para el PDF"""
    timestamp_micro = int(time.time() * 1000000)
    hash_parte = hashlib.md5(f"{cufe}_{nav_id}_{timestamp_micro}".encode()).hexdigest()[:12]
    return f"FACTURA_{cufe[:20]}_{hash_parte}.pdf"


class CloudflareBypass:
    """Bypass para verificación Cloudflare/Turnstile con timeout adaptativo.

    Estado interno por instancia (= por navegador):
      _desafios_resueltos  : cuántos desafíos reales se han resuelto en la sesión
      _llamadas_sin_desafio: llamadas consecutivas donde NO apareció iframe CF
      _desafio_en_ultimo   : True si en la llamada anterior hubo iframe activo
    """

    # Umbrales del timeout adaptativo
    _T_PRIMERA_LLAMADA   = 8   # sesión nueva, CF puede estar activo
    _T_SESION_VALIDADA   = 2   # ya resolvió ≥1 desafío, pocas chances
    _T_SESION_ESTABLECIDA = 1  # >5 llamadas consecutivas sin desafío
    _T_REACTIVACION      = 6   # CF se activó de nuevo en llamada anterior

    def __init__(self, page, nav_id):
        self.page = page
        self.nav_id = nav_id
        self._desafios_resueltos   = 0
        self._llamadas_sin_desafio = 0
        self._desafio_en_ultimo    = False

    def reset(self):
        """Reinicia el estado adaptativo. Llamar cuando el navegador se reinicia."""
        self._desafios_resueltos   = 0
        self._llamadas_sin_desafio = 0
        self._desafio_en_ultimo    = False
        log(self.nav_id, "🔄 Bypass: estado reiniciado", "DEBUG")

    def _timeout_adaptativo(self, timeout_caller: int) -> int:
        """Calcula el timeout óptimo según el historial de la sesión.

        Reglas (en orden de prioridad):
          1. Si el caller pasa un timeout > al adaptativo → respetar el del caller
          2. Si hubo desafío en la última llamada  → T_REACTIVACION
          3. Si lleva >5 llamadas sin desafío       → T_SESION_ESTABLECIDA
          4. Si ya resolvió ≥1 desafío antes        → T_SESION_VALIDADA
          5. Primera llamada / estado base           → T_PRIMERA_LLAMADA
        """
        if self._desafio_en_ultimo:
            adaptativo = self._T_REACTIVACION
        elif self._llamadas_sin_desafio > 5:
            adaptativo = self._T_SESION_ESTABLECIDA
        elif self._desafios_resueltos >= 1:
            adaptativo = self._T_SESION_VALIDADA
        else:
            adaptativo = self._T_PRIMERA_LLAMADA

        # El caller puede forzar un timeout mayor; nunca reducirlo por debajo del adaptativo
        resultado = max(adaptativo, timeout_caller) if timeout_caller > adaptativo else adaptativo
        return resultado

    def intentar(self, timeout=8, max_intentos=2):
        """Intenta resolver Cloudflare/Turnstile.

        El timeout efectivo se calcula adaptativamente: si la sesión ya está
        validada se usa un timeout mucho menor, acelerando CUFEs posteriores.
        Si el caller pasa un timeout mayor al adaptativo, se respeta el del caller.
        Los timeouts internos (resolución del desafío) no cambian.
        """
        timeout_efectivo = self._timeout_adaptativo(timeout)

        for intento in range(max_intentos):
            try:
                iframe = self.page.ele('css:iframe[src*="cloudflare"]', timeout=timeout_efectivo)
                if not iframe:
                    # No hubo desafío: actualizar contadores
                    self._llamadas_sin_desafio += 1
                    self._desafio_en_ultimo = False
                    return True

                # Hay iframe activo: registrar que hubo desafío
                self._desafio_en_ultimo = True
                self._llamadas_sin_desafio = 0

                body = iframe.ele('tag:body', timeout=3)
                if not body or not body.shadow_root:
                    time.sleep(1)
                    continue

                checkbox = body.shadow_root.ele('tag:input', timeout=2)
                if not checkbox:
                    time.sleep(1)
                    continue

                if checkbox.states.is_checked:
                    self._desafios_resueltos += 1
                    self._desafio_en_ultimo = False
                    return True

                checkbox.click()
                time.sleep(4)

                if checkbox.states.is_checked:
                    self._desafios_resueltos += 1
                    self._desafio_en_ultimo = False
                    log(self.nav_id, "✓ Validado", "DEBUG")
                    return True

            except:
                if intento < max_intentos - 1:
                    time.sleep(2)

        return False


def configurar_perfil_persistente(valor: bool):
    """Permite al caller forzar perfil persistente (True) o temporal (False).
    Si no se llama, el comportamiento es automático: True en Windows, False en Linux.
    """
    global _perfil_persistente
    _perfil_persistente = valor


def _encontrar_navegador_windows() -> str:
    """Busca Chrome o Edge instalado localmente en Windows (en orden de preferencia).

    Returns:
        Ruta al ejecutable encontrado, o None si no hay ninguno o no es Windows.
    """
    if platform.system() != 'Windows':
        return None

    localappdata = os.environ.get('LOCALAPPDATA', '')
    rutas_candidatas = [
        r'C:/Program Files/Google/Chrome/Application/chrome.exe',
        r'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
        r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
        r'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
        os.path.join(localappdata, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ]

    for ruta in rutas_candidatas:
        if ruta and os.path.isfile(ruta):
            return ruta

    return None


def _obtener_carpeta_perfil_persistente(nav_id: int) -> str:
    """Retorna la ruta del perfil persistente en Windows.
    Cada nav_id tiene su propia subcarpeta para evitar conflictos entre instancias.
    """
    appdata = os.environ.get('APPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming'))
    return os.path.join(appdata, 'CUFE_DIAN', 'browser_profile', f'nav_{nav_id}')


def _limpiar_locks_perfil(user_data: str, nav_id: int):
    """Elimina archivos Singleton huérfanos del perfil Chrome antes de lanzar.
    Solo borra archivos de coordinación de proceso — nunca cookies ni datos de sesión.
    """
    for nombre in ('SingletonLock', 'SingletonSocket', 'SingletonCookie'):
        ruta = os.path.join(user_data, nombre)
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
                log(nav_id, f"🔓 {nombre} limpiado", "DEBUG")
        except Exception:
            pass


def _liberar_puerto_chrome(port: int, nav_id: int):
    """Mata procesos Chrome/Edge zombi escuchando en el puerto de debug CDP.
    Solo actúa en Windows y solo si el proceso es chrome.exe o msedge.exe.
    """
    if platform.system() != 'Windows':
        return
    try:
        import subprocess
        r = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                pid = line.strip().split()[-1]
                r2 = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, timeout=5
                )
                proc = r2.stdout.lower()
                if 'chrome' in proc or 'msedge' in proc:
                    subprocess.run(['taskkill', '/F', '/PID', pid],
                                   capture_output=True, timeout=5)
                    log(nav_id, f"⚠️ Chrome zombi PID {pid} en :{port} liberado", "WARN")
                    time.sleep(1)
                break
    except Exception:
        pass


def inicializar_navegador(nav_id: int, carpeta_pdfs: str, dian_url: str, headless: bool = False):
    """
    Inicializa navegador Chrome con configuración de descarga
    
    Args:
        nav_id: ID del navegador
        carpeta_pdfs: Carpeta destino de PDFs
        dian_url: URL del portal DIAN
        headless: Si True, ejecuta sin ventana visible
    
    Returns:
        tuple: (ChromiumPage, CloudflareBypass) o (None, None) si falla
    """
    log(nav_id, "🌐 Iniciando...", "INFO")

    port = 9700 + (nav_id * 5)
    _es_windows = platform.system() == 'Windows'

    # ── Perfil del navegador ──────────────────────────────────────────────
    # En Windows: perfil persistente por defecto (Cloudflare reconoce sesiones
    # conocidas y reduce los desafíos en ejecuciones posteriores).
    # En Linux: carpeta temporal (comportamiento original).
    _usar_persistente = _perfil_persistente if _perfil_persistente is not None else _es_windows

    if _usar_persistente and _es_windows:
        user_data = _obtener_carpeta_perfil_persistente(nav_id)
        os.makedirs(user_data, exist_ok=True)
        log(nav_id, f"🗂️ Perfil persistente: ...nav_{nav_id}", "INFO")
    else:
        user_data = obtener_carpeta_chrome(nav_id)
    # ─────────────────────────────────────────────────────────────────────

    co = ChromiumOptions()
    co.set_local_port(port)
    co.headless(headless)

    # ── Navegador instalado en Windows ───────────────────────────────────
    # El Chromium empaquetado por PyInstaller carece de historial y perfil real,
    # lo que Cloudflare detecta como bot. Usar Chrome/Edge del sistema resuelve esto.
    navegador_bin = _encontrar_navegador_windows()
    if navegador_bin:
        nombre_nav = 'Edge' if 'msedge' in navegador_bin.lower() else 'Chrome'
        log(nav_id, f"✅ Usando {nombre_nav} del sistema", "INFO")
        co.set_paths(browser_path=navegador_bin)
    # Si no encuentra ninguno, DrissionPage usa su Chromium empaquetado (sin cambios)
    # ─────────────────────────────────────────────────────────────────────

    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-software-rasterizer')
    co.set_argument('--disable-extensions')
    co.set_argument('--disable-sync')
    co.set_argument('--disable-translate')
    co.set_argument('--disable-background-networking')
    co.set_argument('--disable-default-apps')
    co.set_argument('--window-size=800,600')
    co.set_argument(f'--user-data-dir={user_data}')
    co.set_argument('--disable-blink-features=AutomationControlled')

    # Posición fuera de pantalla
    co.set_argument('--window-position=-2000,-2000')

    # Fix v3.7.1: limpiar locks huérfanos y puerto antes de lanzar
    _limpiar_locks_perfil(user_data, nav_id)
    _liberar_puerto_chrome(port, nav_id)

    os.makedirs(carpeta_pdfs, exist_ok=True)
    ruta_absoluta = os.path.abspath(carpeta_pdfs)
    co.set_download_path(ruta_absoluta)

    # Forzar descarga automática de PDFs
    co.set_pref('download.default_directory', ruta_absoluta)
    co.set_pref('download.prompt_for_download', False)
    co.set_pref('plugins.always_open_pdf_externally', True)
    
    try:
        page = ChromiumPage(addr_or_opts=co)
        page.set.timeouts(20)
        page.set.download_path(ruta_absoluta)
        
        # Registrar navegador activo
        with lock_navegadores:
            navegadores_activos[nav_id] = page
        
        # Crear bypass
        bypass = CloudflareBypass(page, nav_id)
        
        # Navegar a DIAN
        log(nav_id, "🌐 Primera navegación...", "INFO")
        page.get(dian_url)
        time.sleep(2)
        bypass.intentar()
        
        log(nav_id, f"✓ OK (:{port})", "OK")
        return page, bypass
        
    except Exception as e:
        log(nav_id, f"❌ Error: {e}", "ERROR")
        return None, None


def cerrar_navegador(nav_id: int):
    """Cierra un navegador específico y limpia su carpeta"""
    with lock_navegadores:
        if nav_id in navegadores_activos:
            try:
                navegadores_activos[nav_id].quit()
                log(nav_id, "Navegador cerrado", "INFO")
            except:
                pass
            del navegadores_activos[nav_id]
    
    # Limpiar carpeta de este navegador
    carpeta = obtener_carpeta_chrome(nav_id)
    try:
        if os.path.exists(carpeta):
            shutil.rmtree(carpeta, ignore_errors=True)
    except:
        pass


def extraer_eventos(page, nav_id):
    """Busca y extrae los códigos de eventos (RADIAN) de la tabla visible"""
    try:
        # 1. Buscamos si existe el título de la sección
        # Usamos un timeout bajo (1s) para no perder tiempo si no tiene eventos
        if page.ele('text:Eventos de la factura', timeout=0.5):
            
            # 2. Buscamos las tablas presentes
            tablas = page.eles('tag:table')
            for tabla in tablas:
                # Verificamos si es la tabla correcta mirando su encabezado
                if 'Código' in tabla.text or 'Codigo' in tabla.text:
                    codigos = []
                    filas = tabla.eles('tag:tr')
                    
                    # 3. Iteramos las filas (saltando la primera que es el encabezado)
                    for fila in filas[1:]: 
                        celdas = fila.eles('tag:td')
                        # El código siempre está en la columna 0 y es numérico
                        if celdas and celdas[0].text.strip().isdigit():
                            codigos.append(celdas[0].text.strip())
                    
                    if codigos:
                        resultado = ",".join(codigos)
                        log(nav_id, f"📋 Eventos encontrados: {resultado}", "INFO")
                        return resultado
    except Exception as e:
        # Si falla algo estético, no detenemos el proceso, solo logueamos warning
        # log(nav_id, f"Nota eventos: {str(e)[:50]}", "WARN")
        pass
        
    return "" # Si no encuentra nada, devuelve vacío

def detectar_tipo_documento(page, nav_id):
    """
    Detecta el tipo de documento electrónico desde el HTML de la DIAN
    
    Busca el título del documento en la página web y lo clasifica según
    los tipos estándar de facturación electrónica en Colombia.
    
    Args:
        page: Instancia de ChromiumPage con la página cargada
        nav_id: ID del navegador (para logging)
    
    Returns:
        dict: {
            'tipo': str,      # Tipo principal del documento
            'subtipo': str,   # Subtipo específico (si aplica)
            'titulo': str     # Título original encontrado en el HTML
        }
    
    Tipos detectados:
        - FACTURA_ELECTRONICA: Factura electrónica estándar
        - FACTURA_CONTINGENCIA: Factura de contingencia
        - DOC_EQUIVALENTE: Documento equivalente (POS, Transporte, etc.)
        - NOTA_AJUSTE: Nota de ajuste al documento soporte
        - NOTA_CREDITO: Nota crédito
        - NOTA_DEBITO: Nota débito
        - DESCONOCIDO: No se pudo determinar el tipo
    """
    try:
        titulo = ""
        
        # Intentar varios selectores donde la DIAN coloca el título del documento
        selectores_titulo = [
            'tag:h3',           # Más común en páginas de validación
            'tag:h2',           # Algunas versiones usan h2
            'tag:h4',           # Versiones más antiguas
            'tag:h1',           # Por si acaso
        ]
        
        for selector in selectores_titulo:
            try:
                elem = page.ele(selector, timeout=1)
                if elem:
                    texto = elem.text.strip()
                    # Validar que sea un título real (no vacío ni muy corto)
                    if len(texto) > 5 and len(texto) < 200:
                        titulo = texto
                        break
            except:
                continue
        
        # Si no encontramos título con selectores, buscar en el HTML
        if not titulo:
            try:
                import re
                # Obtener primeros 3000 caracteres del HTML (suficiente para el header)
                html_texto = page.html[:3000]
                
                # Patrones de títulos comunes en la DIAN
                patrones = [
                    r'<h[1-4][^>]*>(Factura [Ee]lectrónica[^<]*)</h[1-4]>',
                    r'<h[1-4][^>]*>(Documento [Ee]quivalente[^<]*)</h[1-4]>',
                    r'<h[1-4][^>]*>(Nota de [a-záéíóú]+[^<]*)</h[1-4]>',
                ]
                
                for patron in patrones:
                    m = re.search(patron, html_texto, re.IGNORECASE)
                    if m:
                        titulo = m.group(1).strip()
                        break
            except:
                pass
        
        # Si definitivamente no encontramos título, retornar desconocido
        if not titulo:
            return {
                'tipo': 'DESCONOCIDO',
                'subtipo': '',
                'titulo': ''
            }
        
        # CLASIFICAR SEGÚN EL TÍTULO ENCONTRADO
        info = {
            'tipo': 'DESCONOCIDO',
            'subtipo': '',
            'titulo': titulo
        }
        
        titulo_lower = titulo.lower()
        
        # === DETECCIÓN DE FACTURA ELECTRÓNICA ===
        if 'factura' in titulo_lower and 'electr' in titulo_lower:
            if 'contingencia' in titulo_lower:
                info['tipo'] = 'FACTURA_CONTINGENCIA'
            else:
                info['tipo'] = 'FACTURA_ELECTRONICA'
        
        # === DETECCIÓN DE DOCUMENTO EQUIVALENTE ===
        elif 'documento equivalente' in titulo_lower or 'doc equivalente' in titulo_lower:
            info['tipo'] = 'DOC_EQUIVALENTE'
            
            # Detectar subtipos específicos
            if 'pos' in titulo_lower:
                info['subtipo'] = 'POS'
            elif 'transporte' in titulo_lower:
                if 'aéreo' in titulo_lower or 'aereo' in titulo_lower:
                    info['subtipo'] = 'TRANSPORTE_AEREO'
                elif 'terrestre' in titulo_lower:
                    info['subtipo'] = 'TRANSPORTE_TERRESTRE'
                else:
                    info['subtipo'] = 'TRANSPORTE'
        
        # === DETECCIÓN DE NOTAS ===
        elif 'nota' in titulo_lower:
            if 'ajuste' in titulo_lower:
                info['tipo'] = 'NOTA_AJUSTE'
            elif 'crédito' in titulo_lower or 'credito' in titulo_lower:
                info['tipo'] = 'NOTA_CREDITO'
            elif 'débito' in titulo_lower or 'debito' in titulo_lower:
                info['tipo'] = 'NOTA_DEBITO'
            else:
                # Nota genérica
                info['tipo'] = 'NOTA'
        
        # Logging solo si se detectó algo
        if info['tipo'] != 'DESCONOCIDO':
            subtipo_str = f" ({info['subtipo']})" if info['subtipo'] else ""
            log(nav_id, f"📄 Tipo: {info['tipo']}{subtipo_str}", "INFO")
        
        return info
        
    except Exception as e:
        # Si ocurre cualquier error, retornar tipo desconocido
        # No logueamos el error para no saturar logs con problemas no críticos
        return {
            'tipo': 'DESCONOCIDO',
            'subtipo': '',
            'titulo': ''
        }


def detectar_pdf(cufe: str, nav_id: int, archivos_antes: set, carpeta_pdfs: str, timeout: int = 20) -> str:
    """
    Detecta archivo PDF nuevo que coincida con el CUFE y lo renombra
    """
    log(nav_id, f"⏳ Esperando PDF ({timeout}s)...", "INFO")
    
    tiempo_inicio = time.time()
    cufe_parcial = cufe[:20]
    carpeta_abs = os.path.abspath(carpeta_pdfs)
    
    while (time.time() - tiempo_inicio) < timeout:
        time.sleep(0.5)
        
        try:
            archivos_ahora = set(os.listdir(carpeta_abs))
            archivos_nuevos = archivos_ahora - archivos_antes
            
            pdfs_cufe = [
                f for f in archivos_nuevos 
                if f.endswith('.pdf') and cufe_parcial in f and not f.endswith('.crdownload')
            ]
            
            if pdfs_cufe:
                pdf_nombre = pdfs_cufe[0]
                ruta_pdf = os.path.join(carpeta_abs, pdf_nombre)
                
                try:
                    tamanio = os.path.getsize(ruta_pdf)
                except:
                    continue
                
                if tamanio > 1000:
                    nombre_nuevo = generar_nombre_unico(cufe, nav_id)
                    ruta_nueva = os.path.join(carpeta_abs, nombre_nuevo)
                    
                    try:
                        os.rename(ruta_pdf, ruta_nueva)
                        log(nav_id, f"✓ {nombre_nuevo}", "OK")
                        
                        with lock_mapping:
                            mapping_cufes[cufe] = nombre_nuevo
                        
                        guardar_mapping()
                        return ruta_nueva
                    except:
                        return ruta_pdf
                        
        except:
            continue
    
    log(nav_id, f"❌ TIMEOUT", "ERROR")
    return None


def _inicializar_metricas() -> str:
    """Crea el CSV de métricas al primer CUFE del proceso. Retorna la ruta."""
    global _archivo_metricas
    if _archivo_metricas is not None:
        return _archivo_metricas
    with _lock_metricas:
        if _archivo_metricas is not None:   # double-check tras adquirir lock
            return _archivo_metricas
        os.makedirs('resultado', exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        ruta = os.path.join('resultado', f'metricas_{ts}.csv')
        with open(ruta, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                'nav_id', 'cufe_num', 't_carga', 't_bypass',
                't_input', 't_descarga', 't_total', 'estado', 'timestamp'
            ])
        _archivo_metricas = ruta
        log(0, f"📊 Métricas en: {ruta}", "INFO")
    return _archivo_metricas


def _guardar_metrica(nav_id: int, cufe_num: int, t_carga: float, t_bypass: float,
                     t_input: float, t_descarga: float, t_total: float,
                     estado: str, timestamp: str):
    """Añade una línea al CSV de métricas. Thread-safe."""
    try:
        archivo = _inicializar_metricas()
        with _lock_metricas:
            with open(archivo, 'a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    nav_id, cufe_num,
                    f'{t_carga:.3f}', f'{t_bypass:.3f}',
                    f'{t_input:.3f}', f'{t_descarga:.3f}',
                    f'{t_total:.3f}', estado, timestamp
                ])
    except Exception as exc:
        log(0, f"⚠️ Error guardando métrica: {exc}", "WARN")


def _buscar_campo_nit(page, nav_id: int, timeout_total: float = 8.0):
    """
    Busca el campo NIT del portal DIAN con múltiples selectores CSS de fallback.
    El campo solo aparece después de ingresar el CUFE; se espera su aparición.
    """
    selectores = [
        '#Nit',
        '#DocumentNit',
        '#nitNumber',
        '#nit',
        'css:input[id*="nit" i]',
        'css:input[name*="nit" i]',
        'css:input[placeholder*="NIT" i]',
        'css:input[placeholder*="nit" i]',
    ]
    tiempo_por_selector = max(1.0, timeout_total / len(selectores))
    for sel in selectores:
        try:
            campo = page.ele(sel, timeout=tiempo_por_selector)
            if campo:
                log(nav_id, f"✓ Campo NIT: {sel}", "DEBUG")
                return campo
        except Exception:
            pass
    return None


def _detectar_bloqueo_robot(page) -> bool:
    """Verifica si el portal DIAN mostró el mensaje de bloqueo anti-robot."""
    textos_bloqueo = [
        'Solicitud bloqueada',
        'controles de seguridad',
        'verificación de que el usuario es humano',
        'Request blocked',
    ]
    for texto in textos_bloqueo:
        try:
            if page.ele(f'text:{texto}', timeout=0.8):
                return True
        except Exception:
            pass
    return False


def descargar_cufe(page, bypass, cufe: str, nit: str, numero: int, total: int, nav_id: int,
                   carpeta_pdfs: str, intento: int = 1, max_reintentos: int = 2) -> dict:
    """
    Descarga un CUFE específico.
    Registra métricas de tiempo por etapa en resultado/metricas_YYYYMMDD_HHMMSS.csv
    """
    if intento > 1:
        log(nav_id, "="*50, "RETRY")
        log(nav_id, f"🔄 REINTENTO {intento}/{max_reintentos}", "RETRY")
        log(nav_id, f"📥 CUFE {numero}/{total}", "RETRY")
        log(nav_id, "="*50, "RETRY")
    else:
        log(nav_id, "="*50, "INFO")
        log(nav_id, f"📥 CUFE {numero}/{total}", "INFO")
        log(nav_id, "="*50, "INFO")

    resultado = {
        'numero': numero,
        'cufe': cufe,
        'nit': nit,
        'estado': 'error',
        'pdf': None,
        'ruta_pdf': None,
        'eventos': '',
        'mensaje': '',
        'intento': intento,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # ── Marcadores de telemetría ──────────────────────────────────────────
    _tm_inicio    = time.time()
    _tm_carga_fin = 0.0   # se fija tras page.ele('#DocumentKey')
    _tm_input_ini = 0.0   # se fija al empezar a escribir el CUFE
    _tm_input_fin = 0.0   # se fija antes del loop de búsqueda de botón PDF
    _tm_desc_ini  = 0.0   # se fija al entrar al loop del botón PDF
    _tm_desc_fin  = 0.0   # se fija tras detectar_pdf()
    _tm_bypass    = 0.0   # acumulado de todas las llamadas a bypass.intentar()
    # ─────────────────────────────────────────────────────────────────────

    carpeta_abs = os.path.abspath(carpeta_pdfs)
    archivos_antes = set(os.listdir(carpeta_abs))

    try:
        dian_url = "https://catalogo-vpfe.dian.gov.co/User/SearchDocument"
        if "SearchDocument" not in page.url:
            page.get(dian_url)
            time.sleep(2)
            _t0 = time.time()
            bypass.intentar()
            _tm_bypass += time.time() - _t0

        # ── fin etapa CARGA ───────────────────────────────────────────────
        campo_cufe = page.ele('#DocumentKey', timeout=8)
        _tm_carga_fin = time.time()
        # ─────────────────────────────────────────────────────────────────

        if not campo_cufe:
            resultado['mensaje'] = "Campo CUFE no encontrado"
            resultado['estado'] = 'retry'
            return resultado

        # ── inicio etapa INPUT ────────────────────────────────────────────
        _tm_input_ini = time.time()

        log(nav_id, "⌨️ Ingresando CUFE...", "INFO")
        campo_cufe.clear()
        _esperar(lambda: not (campo_cufe.prop('value') or '').strip(), timeout=1.0)
        campo_cufe.input(cufe, clear=True)
        _esperar(lambda: len(campo_cufe.prop('value') or '') > 10, timeout=3.0)

        # ── Esperar y llenar campo NIT (aparece tras ingresar el CUFE) ────
        log(nav_id, "⌨️ Esperando campo NIT...", "INFO")
        campo_nit = _buscar_campo_nit(page, nav_id, timeout_total=8.0)
        if not campo_nit:
            _tm_input_fin = time.time()
            resultado['mensaje'] = "Campo NIT no encontrado"
            resultado['estado'] = 'retry'
            return resultado

        campo_nit.clear()
        _esperar(lambda: not (campo_nit.prop('value') or '').strip(), timeout=1.0)
        campo_nit.input(nit, clear=True)
        _esperar(lambda: len(campo_nit.prop('value') or '') > 2, timeout=3.0)
        log(nav_id, f"✓ NIT ingresado", "INFO")
        # ─────────────────────────────────────────────────────────────────

        _t0 = time.time()
        bypass.intentar(timeout=10)
        _tm_bypass += time.time() - _t0

        time.sleep(1.5)

        # Verificar bloqueo anti-robot antes de buscar
        if _detectar_bloqueo_robot(page):
            log(nav_id, "🚫 BLOQUEADO por controles anti-robot", "WARN")
            _tm_input_fin = time.time()
            resultado['mensaje'] = "Bloqueado anti-robot DIAN"
            resultado['estado'] = 'bloqueado_robot'
            return resultado

        boton_buscar = page.ele('css:button.search-document', timeout=8)
        if not boton_buscar:
            _tm_input_fin = time.time()
            resultado['mensaje'] = "Botón búsqueda no encontrado"
            resultado['estado'] = 'retry'
            return resultado

        log(nav_id, "🔍 Buscando...", "INFO")
        boton_buscar.click()
        time.sleep(0.5)

        _t0 = time.time()
        bypass.intentar(timeout=10)
        _tm_bypass += time.time() - _t0

        time.sleep(1)

        # Verificar bloqueo anti-robot tras la búsqueda
        if _detectar_bloqueo_robot(page):
            log(nav_id, "🚫 BLOQUEADO por controles anti-robot (post-búsqueda)", "WARN")
            _tm_input_fin = time.time()
            resultado['mensaje'] = "Bloqueado anti-robot DIAN"
            resultado['estado'] = 'bloqueado_robot'
            return resultado

        eventos_encontrados = extraer_eventos(page, nav_id)
        resultado['eventos'] = eventos_encontrados

        tipo_doc = detectar_tipo_documento(page, nav_id)
        resultado['tipo_documento'] = tipo_doc

        # ── fin etapa INPUT ───────────────────────────────────────────────
        _tm_input_fin = time.time()
        # ─────────────────────────────────────────────────────────────────

        log(nav_id, "🔎 Buscando PDF...", "INFO")

        # ── inicio etapa DESCARGA ─────────────────────────────────────────
        _tm_desc_ini = time.time()

        # MEJORADO: Buscar botón PDF primero, con más tiempo
        # Solo declarar "no encontrado" si después de buscar no hay botón
        boton_pdf = None
        tiempo_busqueda = time.time()
        timeout_pdf = 35  # Tiempo suficiente para páginas lentas
        documento_no_encontrado = False

        while not boton_pdf and (time.time() - tiempo_busqueda) < timeout_pdf:
            try:
                # Verificar si apareció mensaje de "no encontrado"
                if page.ele('text:Documento no encontrado', timeout=1):
                    documento_no_encontrado = True
                    break

                # Buscar botón de descarga
                botones = page.eles('tag:a', timeout=2)
                for boton in botones:
                    texto = boton.text.lower()
                    if ("descargar" in texto and "pdf" in texto) or "descargar pdf" in texto:
                        boton_pdf = boton
                        log(nav_id, f"✓ Botón encontrado", "OK")
                        break

                if not boton_pdf:
                    time.sleep(2)

            except:
                time.sleep(2)

        # Si se detectó "no encontrado" durante la búsqueda
        if documento_no_encontrado:
            log(nav_id, "⚠️ NO ENCONTRADO", "WARN")
            resultado['estado'] = 'no_encontrado'
            resultado['mensaje'] = "No existe en DIAN"
            _tm_desc_fin = time.time()
            return resultado

        if not boton_pdf:
            log(nav_id, "❌ Botón PDF no apareció", "ERROR")
            resultado['mensaje'] = "Timeout botón PDF"
            resultado['estado'] = 'retry'
            _tm_desc_fin = time.time()
            return resultado

        log(nav_id, "📥 Descargando...", "INFO")
        _t0 = time.time()
        bypass.intentar(timeout=5)
        _tm_bypass += time.time() - _t0

        time.sleep(1)

        boton_pdf.click()
        log(nav_id, "✓ Click descarga", "OK")

        # ── Popup "Aceptar" — modal Bootbox de contraseña PDF ────────────
        # El portal muestra div.modal-download-info con aviso de contraseña.
        # El botón "Aceptar" vive en el .modal-footer de ese modal.
        # Si no se confirma, el proceso queda bloqueado y no descarga nada.
        try:
            modal_visible = _esperar(
                lambda: bool(page.ele('css:.modal-download-info.in', timeout=0.3)),
                timeout=6.0
            )
            if modal_visible:
                boton_aceptar = page.ele('css:.modal-download-info .modal-footer button', timeout=3)
                if not boton_aceptar:
                    boton_aceptar = page.ele('css:.modal-download-info button', timeout=2)
                if boton_aceptar:
                    boton_aceptar.click()
                    log(nav_id, "✓ Modal 'Aceptar' confirmado", "OK")
                    time.sleep(0.3)
                else:
                    log(nav_id, "⚠️ Modal visible pero botón Aceptar no encontrado", "WARN")
            else:
                log(nav_id, "ℹ️ Modal de contraseña no apareció — continuando", "DEBUG")
        except Exception as e:
            log(nav_id, f"⚠️ Error en popup Aceptar: {str(e)[:40]}", "WARN")
        # ─────────────────────────────────────────────────────────────────

        time.sleep(0.2)

        ruta_pdf = detectar_pdf(cufe, nav_id, archivos_antes, carpeta_pdfs, timeout=20)

        # ── fin etapa DESCARGA ────────────────────────────────────────────
        _tm_desc_fin = time.time()
        # ─────────────────────────────────────────────────────────────────

        if ruta_pdf:
            log(nav_id, "✅ EXITOSO", "OK")
            resultado['estado'] = 'exitoso'
            resultado['pdf'] = os.path.basename(ruta_pdf)
            resultado['ruta_pdf'] = ruta_pdf
            resultado['mensaje'] = "OK"
        else:
            log(nav_id, "❌ PDF no detectado", "ERROR")
            resultado['mensaje'] = "Timeout PDF"
            resultado['estado'] = 'retry'

    except Exception as e:
        log(nav_id, f"❌ Error: {str(e)[:50]}", "ERROR")
        resultado['mensaje'] = f"Error: {str(e)[:80]}"
        resultado['estado'] = 'retry'

    finally:
        # Siempre se ejecuta: en returns normales, returns anticipados y excepciones
        _tm_fin = time.time()
        _guardar_metrica(
            nav_id=nav_id,
            cufe_num=numero,
            t_carga=(_tm_carga_fin - _tm_inicio) if _tm_carga_fin else (_tm_fin - _tm_inicio),
            t_bypass=_tm_bypass,
            t_input=(_tm_input_fin - _tm_input_ini) if (_tm_input_fin and _tm_input_ini) else 0.0,
            t_descarga=(_tm_desc_fin - _tm_desc_ini) if (_tm_desc_fin and _tm_desc_ini) else 0.0,
            t_total=_tm_fin - _tm_inicio,
            estado=resultado['estado'],
            timestamp=resultado['timestamp']
        )

    return resultado


def limpiar_navegadores():
    """Cierra todos los navegadores activos y limpia carpetas"""
    with lock_navegadores:
        for nav_id, page in list(navegadores_activos.items()):
            try:
                page.quit()
            except:
                pass
        navegadores_activos.clear()
    
    # Limpiar todas las carpetas Chrome
    limpiar_carpetas_chrome()


def obtener_navegadores_activos():
    """Retorna la cantidad de navegadores activos"""
    with lock_navegadores:
        return len(navegadores_activos)