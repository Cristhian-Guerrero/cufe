"""
═══════════════════════════════════════════════════════════════════════════
ORQUESTADOR - CUFE DIAN AUTOMATION
Coordina la ejecución paralela de navegadores, reintentos y extractor
v3.6.0 - Navegadores de apoyo dinámicos para reintentos paralelos
═══════════════════════════════════════════════════════════════════════════

MEJORA v3.6.0:
- Cuando un CUFE falla, se crea un navegador de apoyo INMEDIATAMENTE
- Máximo de navegadores de apoyo configurables (default: 5)
- Los reintentos se procesan en paralelo, no secuencialmente
- Reduce tiempo de 26 min a ~5-8 min en Windows con errores
"""

import time
import threading
import queue
from utils import log
from core.descargador import inicializar_navegador, descargar_cufe
from core.extractor import extraer_datos_pdf
from core.excel_generator import generar_excel_final


# Variables globales para callbacks y control
_callback_progreso = None
_callback_mensaje = None
_contador_procesados = 0
_lock_contador = threading.Lock()
_total_cufes = 0
_stop_signal = threading.Event()

# Control de navegadores de apoyo
_navegadores_apoyo_activos = 0
_lock_apoyo = threading.Lock()
MAX_NAVEGADORES_APOYO = 5  # Máximo de navegadores de apoyo simultáneos


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


def _puede_crear_navegador_apoyo():
    """Verifica si se puede crear otro navegador de apoyo"""
    global _navegadores_apoyo_activos
    with _lock_apoyo:
        return _navegadores_apoyo_activos < MAX_NAVEGADORES_APOYO


def _registrar_navegador_apoyo():
    """Registra un nuevo navegador de apoyo"""
    global _navegadores_apoyo_activos
    with _lock_apoyo:
        if _navegadores_apoyo_activos < MAX_NAVEGADORES_APOYO:
            _navegadores_apoyo_activos += 1
            return True
        return False


def _liberar_navegador_apoyo():
    """Libera un navegador de apoyo"""
    global _navegadores_apoyo_activos
    with _lock_apoyo:
        if _navegadores_apoyo_activos > 0:
            _navegadores_apoyo_activos -= 1


def navegador_apoyo_worker(nav_id: int, cufe: str, numero: int, total: int,
                          cola_pdfs: queue.Queue, cola_resultados: queue.Queue,
                          navegadores_activos: list, dian_url: str, carpeta_pdfs: str,
                          max_reintentos: int, intentos_por_cufe: dict, 
                          lock_reintentos: threading.Lock):
    """
    Worker de navegador de apoyo - procesa UN CUFE fallido
    Se crea dinámicamente cuando se detecta un error
    """
    page = None
    
    try:
        log(nav_id, f"🚀 Navegador de apoyo iniciando para CUFE #{numero}", "RETRY")
        
        page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
        
        if page is None:
            log(nav_id, "❌ No se pudo iniciar navegador de apoyo", "ERROR")
            # Marcar como error y notificar
            resultado = {
                'numero': numero,
                'cufe': cufe,
                'estado': 'error',
                'pdf': None,
                'ruta_pdf': None,
                'mensaje': 'No se pudo iniciar navegador de apoyo',
                'intento': max_reintentos
            }
            cola_resultados.put(resultado)
            _notificar_progreso()
            return
        
        navegadores_activos.append(page)
        
        # Obtener intento actual
        with lock_reintentos:
            intento_actual = intentos_por_cufe.get(cufe, 1) + 1
            intentos_por_cufe[cufe] = intento_actual
        
        _notificar_mensaje(f"Reintentando factura {numero}...", "warning")
        
        # Intentar hasta max_reintentos
        while intento_actual <= max_reintentos:
            if _stop_signal.is_set():
                log(nav_id, "⏹️ Detenido por usuario", "WARN")
                break
            
            log(nav_id, f"🔄 Intento {intento_actual}/{max_reintentos} para CUFE #{numero}", "RETRY")
            
            resultado = descargar_cufe(
                page, bypass, cufe, numero, total, nav_id,
                carpeta_pdfs, intento=intento_actual, max_reintentos=max_reintentos
            )
            
            resultado['intento'] = intento_actual
            
            if resultado['estado'] == 'exitoso':
                # ¡Éxito!
                cola_resultados.put(resultado)
                _notificar_progreso()
                
                if resultado['ruta_pdf']:
                    cola_pdfs.put({
                        'numero': numero,
                        'cufe': cufe,
                        'ruta_pdf': resultado['ruta_pdf']
                    })
                    log(nav_id, f"✅ CUFE #{numero} recuperado exitosamente", "OK")
                    _notificar_mensaje(f"Factura {numero} recuperada", "success")
                break
            
            elif resultado['estado'] == 'no_encontrado':
                # No existe en DIAN, no reintentar
                cola_resultados.put(resultado)
                _notificar_progreso()
                _notificar_mensaje(f"Factura {numero}: No registrada en DIAN", "warning")
                break
            
            elif resultado['estado'] == 'retry':
                intento_actual += 1
                with lock_reintentos:
                    intentos_por_cufe[cufe] = intento_actual
                
                if intento_actual > max_reintentos:
                    # Agotados los reintentos
                    resultado['estado'] = 'error'
                    resultado['mensaje'] = f"Falló después de {max_reintentos} intentos"
                    cola_resultados.put(resultado)
                    _notificar_progreso()
                    log(nav_id, f"❌ CUFE #{numero} falló definitivamente", "ERROR")
                    _notificar_mensaje(f"Factura {numero}: Error después de {max_reintentos} intentos", "error")
                else:
                    time.sleep(2)  # Pequeña pausa entre reintentos
            
            else:
                # Otro estado (error directo)
                cola_resultados.put(resultado)
                _notificar_progreso()
                break
        
    except Exception as e:
        log(nav_id, f"Error en navegador de apoyo: {e}", "ERROR")
        # Asegurar que se notifique el resultado aunque sea error
        resultado = {
            'numero': numero,
            'cufe': cufe,
            'estado': 'error',
            'pdf': None,
            'ruta_pdf': None,
            'mensaje': f'Error: {str(e)[:50]}',
            'intento': max_reintentos
        }
        cola_resultados.put(resultado)
        _notificar_progreso()
    
    finally:
        # Cerrar navegador
        if page:
            try:
                page.quit()
                if page in navegadores_activos:
                    navegadores_activos.remove(page)
                log(nav_id, "Navegador de apoyo cerrado", "RETRY")
            except:
                pass
        
        # Liberar slot de navegador de apoyo
        _liberar_navegador_apoyo()


def trabajador_descarga(nav_id: int, cola_trabajo: queue.Queue, cola_reintentos: queue.Queue,
                       cola_pdfs: queue.Queue, cola_resultados: queue.Queue,
                       navegadores_activos: list, dian_url: str, carpeta_pdfs: str,
                       max_reintentos: int, intentos_por_cufe: dict, lock_reintentos: threading.Lock,
                       threads_apoyo: list, lock_threads: threading.Lock):
    """
    Worker de descarga principal
    Ahora puede crear navegadores de apoyo dinámicamente cuando detecta errores
    """
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
        
        nav_apoyo_counter = 0  # Contador local para IDs únicos de navegadores de apoyo
        
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
                    # ¡NUEVO! Intentar crear navegador de apoyo inmediatamente
                    if _puede_crear_navegador_apoyo() and _registrar_navegador_apoyo():
                        nav_apoyo_counter += 1
                        apoyo_id = 100 + (nav_id * 10) + nav_apoyo_counter
                        
                        log(nav_id, f"🚀 Creando navegador de apoyo #{apoyo_id} para CUFE #{numero}", "RETRY")
                        
                        t_apoyo = threading.Thread(
                            target=navegador_apoyo_worker,
                            args=(apoyo_id, cufe, numero, total, cola_pdfs, cola_resultados,
                                  navegadores_activos, dian_url, carpeta_pdfs, max_reintentos,
                                  intentos_por_cufe, lock_reintentos),
                            daemon=True
                        )
                        
                        with lock_threads:
                            threads_apoyo.append(t_apoyo)
                        
                        t_apoyo.start()
                    else:
                        # No hay slots disponibles, enviar a cola tradicional
                        log(nav_id, f"⚠️ Sin slots de apoyo, enviando a cola de reintentos", "RETRY")
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
    """
    Procesador de reintentos tradicional (backup)
    Solo procesa CUFEs que no pudieron ser manejados por navegadores de apoyo
    """
    log(nav_id, "🔄 Procesador de reintentos (backup) iniciado", "RETRY")
    
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
        log(nav_id, f"✓ Procesados {procesados} reintentos (backup)", "RETRY")
    
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
    global _contador_procesados, _total_cufes, _stop_signal, _navegadores_apoyo_activos
    
    _contador_procesados = 0
    _total_cufes = len(cufes)
    _stop_signal.clear()
    _navegadores_apoyo_activos = 0
    
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
    lock_threads = threading.Lock()
    
    navegadores_activos = []
    datos_completos = []
    intentos_por_cufe = {}
    threads_apoyo = []  # Lista para rastrear threads de apoyo
    
    for i, cufe in enumerate(cufes, 1):
        cola_trabajo.put((cufe, i, len(cufes)))
    
    for _ in range(NUM_NAVEGADORES):
        cola_trabajo.put(None)
    
    threads = []
    
    for i in range(1, NUM_NAVEGADORES + 1):
        t = threading.Thread(
            target=trabajador_descarga,
            args=(i, cola_trabajo, cola_reintentos, cola_pdfs, cola_resultados,
                  navegadores_activos, DIAN_URL, CARPETA_PDFS, MAX_REINTENTOS,
                  intentos_por_cufe, lock_reintentos, threads_apoyo, lock_threads)
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
    
    # Esperar a workers principales
    for t in threads[:NUM_NAVEGADORES]:
        t.join()
    
    log(0, "✓ Descargas principales completadas", "OK")
    _notificar_mensaje("Consultas completadas", "success")
    
    # Esperar a todos los navegadores de apoyo
    log(0, f"⏳ Esperando {len(threads_apoyo)} navegadores de apoyo...", "INFO")
    with lock_threads:
        for t_apoyo in threads_apoyo:
            if t_apoyo.is_alive():
                t_apoyo.join(timeout=120)  # Máximo 2 min por navegador de apoyo
    
    log(0, "✓ Navegadores de apoyo completados", "OK")
    
    # Finalizar cola de reintentos (backup)
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
        'num_navegadores': NUM_NAVEGADORES,
        'navegadores_apoyo_usados': len(threads_apoyo)
    }