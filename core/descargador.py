"""
═══════════════════════════════════════════════════════════════════════════
DESCARGADOR CORREGIDO - CUFE DIAN AUTOMATION
Basado en main_backup_v3.3.py - Con renombrado y mapping
v3.5.2 - Corregido: Solo detecta PDFs que coincidan con el CUFE
═══════════════════════════════════════════════════════════════════════════

CAMBIOS CLAVE vs versión anterior:
1. detectar_pdf() SOLO busca PDFs que contengan cufe[:20] en el nombre
2. NO hay fallback a "cualquier PDF nuevo" - esto causaba el desorden
3. Se guarda el mapping cufe -> nombre_archivo
4. Se usa lock para evitar race conditions
"""

import time
import os
import hashlib
import threading
import json
from DrissionPage import ChromiumPage, ChromiumOptions
from utils import log

# === VARIABLES GLOBALES DEL MÓDULO ===
lock_mapping = threading.Lock()
mapping_cufes = {}
navegadores_activos = []
ARCHIVO_MAPPING = "mapping_cufes_pdfs.json"


def guardar_mapping():
    """Guarda mapping JSON de forma segura"""
    with lock_mapping:
        try:
            with open(ARCHIVO_MAPPING, 'w', encoding='utf-8') as f:
                json.dump(mapping_cufes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando mapping: {e}")


def generar_nombre_unico(cufe: str, nav_id: int) -> str:
    """
    Genera nombre único para el PDF
    Formato: FACTURA_{cufe[:20]}_{hash}.pdf
    """
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


def inicializar_navegador(nav_id: int, carpeta_pdfs: str, dian_url: str):
    """
    Inicializa navegador Chrome con configuración de descarga
    
    Args:
        nav_id: ID del navegador
        carpeta_pdfs: Carpeta destino de PDFs
        dian_url: URL del portal DIAN
    
    Returns:
        tuple: (ChromiumPage, CloudflareBypass) o (None, None) si falla
    """
    log(nav_id, "🌐 Iniciando...", "INFO")
    
    port = 9700 + (nav_id * 5)
    user_data = os.path.join(os.getcwd(), f".chrome_dian_{nav_id}")
    
    co = ChromiumOptions()
    co.set_local_port(port)
    co.headless(False)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--window-size=800,600')
    co.set_argument(f'--user-data-dir={user_data}')
    co.set_argument('--disable-blink-features=AutomationControlled')
    
    # Posición fuera de pantalla
    x = -2000
    y = -2000
    co.set_argument(f'--window-position={x},{y}')
    
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
        navegadores_activos.append(page)
        
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


def detectar_pdf(cufe: str, nav_id: int, archivos_antes: set, carpeta_pdfs: str, timeout: int = 20) -> str:
    """
    Detecta archivo PDF nuevo que coincida con el CUFE y lo renombra
    
    IMPORTANTE - IGUAL QUE BACKUP v3.3:
    - SOLO busca PDFs que contengan cufe[:20] en el nombre
    - NO hay fallback a "cualquier PDF nuevo"
    - Esto evita que un navegador tome el PDF de otro
    
    Args:
        cufe: CUFE buscado
        nav_id: ID navegador
        archivos_antes: Set de archivos ANTES de iniciar descarga
        carpeta_pdfs: Carpeta de PDFs
        timeout: Timeout en segundos
    
    Returns:
        Ruta ABSOLUTA del PDF renombrado o None si timeout
    """
    log(nav_id, f"⏳ Esperando PDF ({timeout}s)...", "INFO")
    
    tiempo_inicio = time.time()
    cufe_parcial = cufe[:20]  # Los primeros 20 caracteres del CUFE
    
    # Siempre usar ruta absoluta
    carpeta_abs = os.path.abspath(carpeta_pdfs)
    
    while (time.time() - tiempo_inicio) < timeout:
        time.sleep(0.5)
        
        try:
            archivos_ahora = set(os.listdir(carpeta_abs))
            archivos_nuevos = archivos_ahora - archivos_antes
            
            # CRÍTICO: Solo buscar PDFs que contengan el CUFE parcial
            # NO hay fallback - igual que backup v3.3
            pdfs_cufe = [
                f for f in archivos_nuevos 
                if f.endswith('.pdf') and cufe_parcial in f and not f.endswith('.crdownload')
            ]
            
            if pdfs_cufe:
                pdf_nombre = pdfs_cufe[0]
                ruta_pdf = os.path.join(carpeta_abs, pdf_nombre)
                
                # Verificar tamaño
                try:
                    tamanio = os.path.getsize(ruta_pdf)
                except:
                    continue
                
                if tamanio > 1000:  # Más de 1KB
                    # RENOMBRAR INMEDIATAMENTE
                    nombre_nuevo = generar_nombre_unico(cufe, nav_id)
                    ruta_nueva = os.path.join(carpeta_abs, nombre_nuevo)
                    
                    try:
                        os.rename(ruta_pdf, ruta_nueva)
                        log(nav_id, f"✓ {nombre_nuevo}", "OK")
                        
                        # Guardar en mapping
                        with lock_mapping:
                            mapping_cufes[cufe] = nombre_nuevo
                        
                        # Guardar mapping a disco
                        guardar_mapping()
                        
                        return ruta_nueva
                    except:
                        # Si falla renombrar, devolver original
                        return ruta_pdf
                        
        except:
            continue
    
    log(nav_id, f"❌ TIMEOUT", "ERROR")
    return None


def descargar_cufe(page, bypass, cufe: str, numero: int, total: int, nav_id: int,
                   carpeta_pdfs: str, intento: int = 1, max_reintentos: int = 2) -> dict:
    """
    Descarga un CUFE específico - IGUAL QUE BACKUP v3.3
    
    Args:
        page: ChromiumPage
        bypass: CloudflareBypass instance
        cufe: CUFE a descargar
        numero: Número de orden
        total: Total de CUFEs
        nav_id: ID navegador
        carpeta_pdfs: Carpeta destino
        intento: Número de intento actual
        max_reintentos: Máximo de reintentos permitidos
    
    Returns:
        dict con resultado de la descarga
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
    
    # IMPORTANTE: Capturar archivos ANTES de iniciar (con ruta absoluta)
    carpeta_abs = os.path.abspath(carpeta_pdfs)
    archivos_antes = set(os.listdir(carpeta_abs))
    
    try:
        # Navegar si es necesario
        dian_url = "https://catalogo-vpfe.dian.gov.co/User/SearchDocument"
        if "SearchDocument" not in page.url:
            page.get(dian_url)
            time.sleep(2)
            bypass.intentar()
        
        # Buscar campo CUFE
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
        
        # Buscar botón de búsqueda
        boton_buscar = page.ele('css:button.search-document', timeout=8)
        if not boton_buscar:
            resultado['mensaje'] = "Botón búsqueda no encontrado"
            resultado['estado'] = 'retry'
            return resultado
        
        log(nav_id, "🔍 Buscando...", "INFO")
        boton_buscar.click()
        time.sleep(4)
        
        # Verificar si documento existe
        if page.ele('text:Documento no encontrado', timeout=2):
            log(nav_id, "⚠️ NO ENCONTRADO", "WARN")
            resultado['estado'] = 'no_encontrado'
            resultado['mensaje'] = "No existe en DIAN"
            return resultado
        
        bypass.intentar(timeout=10)
        time.sleep(2)
        
        log(nav_id, "🔎 Buscando PDF...", "INFO")
        
        # Buscar botón de descarga PDF
        boton_pdf = None
        tiempo_busqueda = time.time()
        timeout_pdf = 45
        
        while not boton_pdf and (time.time() - tiempo_busqueda) < timeout_pdf:
            try:
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
        
        # DETECTAR Y RENOMBRAR PDF (solo el que coincide con CUFE)
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
    """Cierra todos los navegadores activos"""
    for page in navegadores_activos:
        try:
            page.quit()
        except:
            pass
    navegadores_activos.clear()