"""
═══════════════════════════════════════════════════════════════════════════
ORQUESTADOR - CUFE DIAN AUTOMATION
Coordina la ejecución paralela de navegadores, reintentos y extractor
v3.5.4 - Con callbacks de progreso para GUI
═══════════════════════════════════════════════════════════════════════════
"""

import time
import threading
import queue
from utils import log
from core.descargador import inicializar_navegador, descargar_cufe
from core.extractor import extraer_datos_pdf
from core.excel_generator import generar_excel_final


# Variable global para callbacks
_callback_progreso = None
_callback_mensaje = None
_contador_procesados = 0
_lock_contador = threading.Lock()
_total_cufes = 0
_stop_signal = threading.Event()


def configurar_callbacks(callback_progreso=None, callback_mensaje=None):
    global _callback_progreso, _callback_mensaje
    _callback_progreso = callback_progreso
    _callback_mensaje = callback_mensaje


def detener_sistema():
    global _stop_signal
    _stop_signal.set()


def _notificar_progreso():
    global _contador_procesados, _total_cufes, _callback_progreso
    
    with _lock_contador:
        _contador_procesados += 1
        actual = _contador_procesados
    
    if _callback_progreso and _total_cufes > 0:
        porcentaje = int((actual / _total_cufes) * 100)
        try:
            _callback_progreso(porcentaje, actual, _total_cufes)
        except:
            pass


def _notificar_mensaje(mensaje, tipo="info"):
    global _callback_mensaje
    if _callback_mensaje:
        try:
            _callback_mensaje(mensaje, tipo)
        except:
            pass


def trabajador_descarga(nav_id: int, cola_trabajo: queue.Queue, cola_reintentos: queue.Queue,
                       cola_pdfs: queue.Queue, cola_resultados: queue.Queue,
                       navegadores_activos: list, dian_url: str, carpeta_pdfs: str,
                       max_reintentos: int):
    page = None
    bypass = None
    
    try:
        if nav_id == 1:
            _notificar_mensaje("Conectando con el portal DIAN...", "info")
        
        page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
        
        if page is None:
            log(nav_id, "❌ No se pudo iniciar navegador", "ERROR")
            return
        
        navegadores_activos.append(page)
        
        if nav_id == 1:
            _notificar_mensaje("Conexión establecida", "success")
        
        while True:
            if _stop_signal.is_set():
                log(nav_id, "⏹️ Detenido por usuario", "WARN")
                break
            
            try:
                item = cola_trabajo.get(timeout=3)
                
                if item is None:
                    log(nav_id, "🏁 Fin", "INFO")
                    break
                
                cufe, numero, total = item
                
                _notificar_mensaje(f"Consultando factura {numero} de {total}...", "info")
                
                resultado = descargar_cufe(
                    page, bypass, cufe, numero, total, nav_id,
                    carpeta_pdfs, intento=1, max_reintentos=max_reintentos
                )
                
                if resultado['estado'] == 'retry':
                    log(nav_id, f"⚠️ Falló, enviando a reintentos...", "RETRY")
                    cola_reintentos.put((cufe, numero, total))
                else:
                    cola_resultados.put(resultado)
                    _notificar_progreso()
                    
                    if resultado['estado'] == 'exitoso' and resultado['ruta_pdf']:
                        cola_pdfs.put({
                            'numero': numero,
                            'cufe': cufe,
                            'ruta_pdf': resultado['ruta_pdf']
                        })
                        log(nav_id, "→ PDF enviado a extractor", "DEBUG")
                        _notificar_mensaje(f"Factura {numero} descargada", "success")
                    elif resultado['estado'] == 'no_encontrado':
                        _notificar_mensaje(f"Factura {numero}: No registrada en DIAN", "warning")
                
                time.sleep(3)
                
            except queue.Empty:
                continue
            except Exception as e:
                log(nav_id, f"Error en worker: {e}", "ERROR")
    
    except Exception as e:
        log(nav_id, f"Error iniciando navegador: {e}", "ERROR")
    
    finally:
        if page:
            try:
                page.quit()
                if page in navegadores_activos:
                    navegadores_activos.remove(page)
                log(nav_id, "Navegador cerrado", "INFO")
            except:
                pass


def procesador_reintentos(nav_id: int, cola_reintentos: queue.Queue, cola_pdfs: queue.Queue,
                         cola_resultados: queue.Queue, navegadores_activos: list,
                         dian_url: str, carpeta_pdfs: str, max_reintentos: int,
                         intentos_por_cufe: dict, lock_reintentos: threading.Lock):
    log(nav_id, "🔄 Procesador de reintentos iniciado", "RETRY")
    
    page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
    
    if page is None:
        log(nav_id, "❌ No se pudo iniciar navegador de reintentos", "ERROR")
        return
    
    navegadores_activos.append(page)
    procesados = 0
    
    while True:
        if _stop_signal.is_set():
            log(nav_id, "⏹️ Detenido por usuario", "WARN")
            break
        
        try:
            item = cola_reintentos.get(timeout=10)
            
            if item is None:
                log(nav_id, "🏁 Fin reintentos", "RETRY")
                break
            
            cufe, numero, total = item
            
            with lock_reintentos:
                intento_actual = intentos_por_cufe.get(cufe, 1) + 1
                intentos_por_cufe[cufe] = intento_actual
            
            log(nav_id, f"🔄 Reintentando CUFE #{numero} (intento {intento_actual}/{max_reintentos})", "RETRY")
            _notificar_mensaje(f"Verificando factura {numero}...", "warning")
            
            resultado = descargar_cufe(
                page, bypass, cufe, numero, total, nav_id,
                carpeta_pdfs, intento=intento_actual, max_reintentos=max_reintentos
            )
            
            resultado['intento'] = intento_actual
            
            if resultado['estado'] == 'retry' and intento_actual < max_reintentos:
                log(nav_id, f"⚠️ Falló de nuevo, reintentando...", "RETRY")
                cola_reintentos.put((cufe, numero, total))
            else:
                if resultado['estado'] == 'retry':
                    resultado['estado'] = 'error'
                
                cola_resultados.put(resultado)
                _notificar_progreso()
                
                if resultado['estado'] == 'exitoso' and resultado['ruta_pdf']:
                    cola_pdfs.put({
                        'numero': numero,
                        'cufe': cufe,
                        'ruta_pdf': resultado['ruta_pdf']
                    })
                    log(nav_id, "✅ REINTENTO EXITOSO", "OK")
                    _notificar_mensaje(f"Factura {numero} recuperada", "success")
            
            procesados += 1
            time.sleep(3)
            
        except queue.Empty:
            continue
        except Exception as e:
            log(nav_id, f"Error reintentos: {e}", "ERROR")
            break
    
    if procesados > 0:
        log(nav_id, f"✓ Procesados {procesados} reintentos", "RETRY")
    
    try:
        page.quit()
        if page in navegadores_activos:
            navegadores_activos.remove(page)
        log(nav_id, "Navegador de reintentos cerrado", "RETRY")
    except:
        pass


def trabajador_extractor(cola_pdfs: queue.Queue, datos_completos: list, 
                        lock_excel: threading.Lock):
    log(99, "🔍 Extractor iniciado", "OK")
    procesados = 0
    
    while True:
        if _stop_signal.is_set():
            break
        
        try:
            item = cola_pdfs.get(timeout=5)
            
            if item is None:
                log(99, "🏁 Fin extractor", "INFO")
                break
            
            numero = item['numero']
            cufe = item['cufe']
            ruta_pdf = item['ruta_pdf']
            
            log(99, f"📄 Extrayendo #{numero}...", "INFO")
            
            datos = extraer_datos_pdf(ruta_pdf, cufe, numero)
            
            with lock_excel:
                datos_completos.append(datos)
            
            procesados += 1
            log(99, f"✓ Procesado #{numero} ({procesados} total)", "OK")
            
        except queue.Empty:
            time.sleep(1)
        except Exception as e:
            log(99, f"Error: {e}", "ERROR")


def ejecutar_sistema(cufes: list, config: dict, callback_progreso=None, callback_mensaje=None):
    global _contador_procesados, _total_cufes, _stop_signal
    
    _contador_procesados = 0
    _total_cufes = len(cufes)
    _stop_signal.clear()
    
    configurar_callbacks(callback_progreso, callback_mensaje)
    
    DIAN_URL = config['dian_url']
    CARPETA_PDFS = config['carpeta_pdfs']
    ARCHIVO_EXCEL = config['archivo_excel']
    NUM_NAVEGADORES = min(len(cufes), config['num_navegadores'])
    MAX_REINTENTOS = config['max_reintentos']
    
    _notificar_mensaje(f"Preparando consulta de {len(cufes)} facturas...", "info")
    
    cola_trabajo = queue.Queue()
    cola_reintentos = queue.Queue()
    cola_pdfs = queue.Queue()
    cola_resultados = queue.Queue()
    
    lock_excel = threading.Lock()
    lock_reintentos = threading.Lock()
    
    navegadores_activos = []
    datos_completos = []
    intentos_por_cufe = {}
    
    for i, cufe in enumerate(cufes, 1):
        cola_trabajo.put((cufe, i, len(cufes)))
    
    for _ in range(NUM_NAVEGADORES):
        cola_trabajo.put(None)
    
    threads = []
    
    for i in range(1, NUM_NAVEGADORES + 1):
        t = threading.Thread(
            target=trabajador_descarga,
            args=(i, cola_trabajo, cola_reintentos, cola_pdfs, cola_resultados,
                  navegadores_activos, DIAN_URL, CARPETA_PDFS, MAX_REINTENTOS)
        )
        threads.append(t)
    
    t_reintentos = threading.Thread(
        target=procesador_reintentos,
        args=(98, cola_reintentos, cola_pdfs, cola_resultados, navegadores_activos,
              DIAN_URL, CARPETA_PDFS, MAX_REINTENTOS, intentos_por_cufe, lock_reintentos)
    )
    threads.append(t_reintentos)
    
    t_extractor = threading.Thread(
        target=trabajador_extractor,
        args=(cola_pdfs, datos_completos, lock_excel)
    )
    threads.append(t_extractor)
    
    tiempo_inicio = time.time()
    log(0, "🎬 Iniciando...", "OK")
    
    for t in threads:
        t.start()
    
    for t in threads[:NUM_NAVEGADORES]:
        t.join()
    
    log(0, "✓ Descargas principales completadas", "OK")
    _notificar_mensaje("Consultas completadas", "success")
    
    cola_reintentos.put(None)
    t_reintentos.join()
    
    log(0, "✓ Reintentos completados", "OK")
    
    cola_pdfs.put(None)
    t_extractor.join()
    
    log(0, "✓ Extracción completada", "OK")
    
    _notificar_mensaje("Generando reporte Excel...", "info")
    generar_excel_final(ARCHIVO_EXCEL, datos_completos)
    _notificar_mensaje("Proceso finalizado", "success")
    
    duracion = time.time() - tiempo_inicio
    
    resultados = []
    while not cola_resultados.empty():
        resultados.append(cola_resultados.get())
            
    resultados.sort(key=lambda x: x['numero'])
    
    configurar_callbacks(None, None)
    
    return {
        'resultados': resultados,
        'datos_completos': datos_completos,
        'duracion': duracion,
        'num_navegadores': NUM_NAVEGADORES
    }