"""
═══════════════════════════════════════════════════════════════════════════
DESCARGADOR - CUFE DIAN AUTOMATION
v3.7.0 - Optimizado: Carpetas temp del sistema, cierre inmediato en error
═══════════════════════════════════════════════════════════════════════════

CAMBIOS v3.7.0:
1. Carpetas Chrome en carpeta temporal configurable (no en cwd)
2. Función para limpiar TODAS las carpetas Chrome al finalizar
3. Navegadores se pueden cerrar individualmente
4. Mejor manejo de recursos en Windows
"""

import time
import os
import hashlib
import threading
import json
import shutil
import tempfile
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


def generar_nombre_unico(cufe: str, nav_id: int) -> str:
    """Genera nombre único para el PDF"""
    timestamp_micro = int(time.time() * 1000000)
    hash_parte = hashlib.md5(f"{cufe}_{nav_id}_{timestamp_micro}".encode()).hexdigest()[:12]
    return f"FACTURA_{cufe[:20]}_{hash_parte}.pdf"


class CloudflareBypass:
    """Bypass para verificación Cloudflare/Turnstile"""
    
    def __init__(self, page, nav_id):
        self.page = page
        self.nav_id = nav_id
    
    def intentar(self, timeout=8, max_intentos=2):
        """Intenta resolver Cloudflare/Turnstile"""
        for intento in range(max_intentos):
            try:
                iframe = self.page.ele('css:iframe[src*="cloudflare"]', timeout=timeout)
                if not iframe:
                    return True
                
                body = iframe.ele('tag:body', timeout=3)
                if not body or not body.shadow_root:
                    time.sleep(1)
                    continue
                
                checkbox = body.shadow_root.ele('tag:input', timeout=2)
                if not checkbox:
                    time.sleep(1)
                    continue
                
                if checkbox.states.is_checked:
                    return True
                
                checkbox.click()
                time.sleep(4)
                
                if checkbox.states.is_checked:
                    log(self.nav_id, "✓ Validado", "DEBUG")
                    return True
                
            except:
                if intento < max_intentos - 1:
                    time.sleep(2)
        
        return False


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
    user_data = obtener_carpeta_chrome(nav_id)
    
    co = ChromiumOptions()
    co.set_local_port(port)
    co.headless(headless)
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
        time.sleep(3)
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


def descargar_cufe(page, bypass, cufe: str, numero: int, total: int, nav_id: int,
                   carpeta_pdfs: str, intento: int = 1, max_reintentos: int = 2) -> dict:
    """
    Descarga un CUFE específico
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
        'estado': 'error',
        'pdf': None,
        'ruta_pdf': None,
        'mensaje': '',
        'intento': intento
    }
    
    carpeta_abs = os.path.abspath(carpeta_pdfs)
    archivos_antes = set(os.listdir(carpeta_abs))
    
    try:
        dian_url = "https://catalogo-vpfe.dian.gov.co/User/SearchDocument"
        if "SearchDocument" not in page.url:
            page.get(dian_url)
            time.sleep(2)
            bypass.intentar()
        
        campo_cufe = page.ele('#DocumentKey', timeout=8)
        if not campo_cufe:
            resultado['mensaje'] = "Campo CUFE no encontrado"
            resultado['estado'] = 'retry'
            return resultado
        
        log(nav_id, "⌨️ Ingresando...", "INFO")
        campo_cufe.clear()
        time.sleep(0.5)
        campo_cufe.input(cufe, clear=True)
        time.sleep(1)
        
        bypass.intentar(timeout=10)
        time.sleep(2)
        
        boton_buscar = page.ele('css:button.search-document', timeout=8)
        if not boton_buscar:
            resultado['mensaje'] = "Botón búsqueda no encontrado"
            resultado['estado'] = 'retry'
            return resultado
        
        log(nav_id, "🔍 Buscando...", "INFO")
        boton_buscar.click()
        time.sleep(3)
        
        bypass.intentar(timeout=10)
        time.sleep(2)
        
        log(nav_id, "🔎 Buscando PDF...", "INFO")
        
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
            return resultado
        
        if not boton_pdf:
            log(nav_id, "❌ Botón PDF no apareció", "ERROR")
            resultado['mensaje'] = "Timeout botón PDF"
            resultado['estado'] = 'retry'
            return resultado
        
        log(nav_id, "📥 Descargando...", "INFO")
        bypass.intentar(timeout=5)
        time.sleep(2)
        
        boton_pdf.click()
        log(nav_id, "✓ Click OK", "OK")
        time.sleep(1)
        
        ruta_pdf = detectar_pdf(cufe, nav_id, archivos_antes, carpeta_pdfs, timeout=20)
        
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