"""
═══════════════════════════════════════════════════════════════════════════
ORQUESTADOR - CUFE DIAN AUTOMATION
v3.7.0 - Optimizado: Cierre inmediato en error, gestión inteligente de recursos
═══════════════════════════════════════════════════════════════════════════

MEJORAS v3.7.0:
1. Navegador con error se CIERRA INMEDIATAMENTE
2. Navegador de apoyo REEMPLAZA al que falló (no se suma)
3. Máximo de navegadores calculado según CUFEs (más eficiente)
4. Limpieza completa de carpetas Chrome al finalizar
5. Mejor rendimiento en Windows
"""

import time
import threading
import queue
import os
from utils import log
from core.descargador import (
    inicializar_navegador, 
    descargar_cufe, 
    cerrar_navegador,
    limpiar_navegadores,
    limpiar_carpetas_chrome,
    configurar_carpeta_chrome
)
from core.extractor import extraer_datos_pdf
from core.excel_generator import generar_excel_final


# Variables globales para callbacks y control
_callback_progreso = None
_callback_mensaje = None
_contador_procesados = 0
_lock_contador = threading.Lock()
_total_cufes = 0
_stop_signal = threading.Event()

# Control de navegadores
_navegadores_en_uso = 0
_max_navegadores = 10
_lock_navegadores = threading.Lock()


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


def _reservar_slot_navegador():
    """Reserva un slot de navegador si hay disponible"""
    global _navegadores_en_uso, _max_navegadores
    with _lock_navegadores:
        if _navegadores_en_uso < _max_navegadores:
            _navegadores_en_uso += 1
            return True
        return False


def _liberar_slot_navegador():
    """Libera un slot de navegador"""
    global _navegadores_en_uso
    with _lock_navegadores:
        if _navegadores_en_uso > 0:
            _navegadores_en_uso -= 1


def _calcular_max_navegadores(num_cufes: int, config_max: int) -> int:
    """
    Calcula el número óptimo de navegadores según la cantidad de CUFEs
    
    Reglas:
    - Mínimo 2 navegadores
    - Máximo según config (default 10)
    - No más navegadores que CUFEs
    - En Windows, limitar a 6-8 para mejor rendimiento
    """
    import platform
    
    # Base: no más navegadores que CUFEs
    optimo = min(num_cufes, config_max)
    
    # En Windows, ser más conservador
    if platform.system() == "Windows":
        optimo = min(optimo, 8)
    
    # Mínimo 2 navegadores
    optimo = max(optimo, 2)
    
    return optimo


def trabajador_descarga(nav_id: int, cola_trabajo: queue.Queue, cola_fallidos: queue.Queue,
                       cola_pdfs: queue.Queue, cola_resultados: queue.Queue,
                       dian_url: str, carpeta_pdfs: str, max_reintentos: int):
    """
    Worker de descarga - Versión optimizada v3.7.1
    
    CAMBIOS:
    - Si falla, pone CUFE en cola para que OTRO navegador lo intente
    - Si hay 2+ fallos consecutivos, reinicia el navegador
    - Guarda nav_id del fallo para evitar que el mismo nav lo retome
    """
    page = None
    bypass = None
    fallos_consecutivos = 0
    MAX_FALLOS_ANTES_REINICIAR = 2
    
    try:
        if nav_id == 1:
            _notificar_mensaje("Conectando con el portal DIAN...", "info")
        
        page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
        
        if page is None:
            log(nav_id, "❌ No se pudo iniciar navegador", "ERROR")
            _liberar_slot_navegador()
            return
        
        if nav_id == 1:
            _notificar_mensaje("Conexión establecida", "success")
        
        while True:
            if _stop_signal.is_set():
                log(nav_id, "⏹️ Detenido por usuario", "WARN")
                break
            
            try:
                # Primero intentar tomar un CUFE fallido (prioridad)
                item = None
                try:
                    item = cola_fallidos.get_nowait()
                    # Verificar si el item tiene nav_anterior
                    if len(item) == 5:
                        cufe, numero, total, intento, nav_anterior = item
                        # Si fue del mismo navegador, devolverlo para que otro lo tome
                        if nav_anterior == nav_id:
                            cola_fallidos.put(item)
                            item = None
                        else:
                            log(nav_id, f"📥 Tomando CUFE #{numero} (fallido en Nav{nav_anterior})", "RETRY")
                    else:
                        log(nav_id, f"📥 Tomando CUFE fallido #{item[1]}", "RETRY")
                except queue.Empty:
                    pass
                
                # Si no hay fallidos (o era del mismo nav), tomar de cola principal
                if item is None:
                    try:
                        item = cola_trabajo.get(timeout=2)
                    except queue.Empty:
                        continue
                
                if item is None:
                    log(nav_id, "🏁 Fin", "INFO")
                    break
                
                # Parsear item según su longitud
                if len(item) == 5:
                    cufe, numero, total, intento, nav_anterior = item
                elif len(item) == 4:
                    cufe, numero, total, intento = item
                else:
                    cufe, numero, total = item
                    intento = 1
                
                _notificar_mensaje(f"Consultando factura {numero} de {total}...", "info")
                
                resultado = descargar_cufe(
                    page, bypass, cufe, numero, total, nav_id,
                    carpeta_pdfs, intento=intento, max_reintentos=max_reintentos
                )
                
                if resultado['estado'] == 'retry':
                    fallos_consecutivos += 1
                    
                    if intento < max_reintentos:
                        # Poner en cola de fallidos con nav_id para que OTRO navegador lo intente
                        cola_fallidos.put((cufe, numero, total, intento + 1, nav_id))
                        log(nav_id, f"⚠️ CUFE #{numero} a cola (intento {intento + 1})", "RETRY")
                        _notificar_mensaje(f"Reintentando factura {numero}...", "warning")
                        
                        # Si hay muchos fallos consecutivos, reiniciar navegador
                        if fallos_consecutivos >= MAX_FALLOS_ANTES_REINICIAR:
                            log(nav_id, f"🔄 Reiniciando navegador ({fallos_consecutivos} fallos)", "WARN")
                            cerrar_navegador(nav_id)
                            time.sleep(2)
                            page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
                            if page is None:
                                log(nav_id, "❌ No se pudo reiniciar navegador", "ERROR")
                                break
                            fallos_consecutivos = 0
                            log(nav_id, "✓ Navegador reiniciado", "OK")
                    else:
                        # Agotados los reintentos
                        resultado['estado'] = 'error'
                        resultado['mensaje'] = f"Falló después de {max_reintentos} intentos"
                        cola_resultados.put(resultado)
                        _notificar_progreso()
                        log(nav_id, f"❌ CUFE #{numero} falló definitivamente", "ERROR")
                        _notificar_mensaje(f"Factura {numero}: Error", "error")
                else:
                    # Éxito o no_encontrado - resetear contador de fallos
                    fallos_consecutivos = 0
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
                        # Agregar a cola de PDFs con marca especial para que el extractor lo registre
                        cola_pdfs.put({
                            'numero': numero,
                            'cufe': cufe,
                            'ruta_pdf': None,
                            'no_encontrado': True
                        })
                        _notificar_mensaje(f"Factura {numero}: No registrada en DIAN", "warning")
                
                time.sleep(2)  # Pausa entre descargas
                
            except Exception as e:
                log(nav_id, f"Error en worker: {e}", "ERROR")
                fallos_consecutivos += 1
    
    except Exception as e:
        log(nav_id, f"Error iniciando navegador: {e}", "ERROR")
    
    finally:
        # Cerrar navegador y liberar recursos
        cerrar_navegador(nav_id)
        _liberar_slot_navegador()


def trabajador_extractor(cola_pdfs: queue.Queue, datos_completos: list, 
                        lock_excel: threading.Lock):
    """Extractor de datos de PDFs"""
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
            ruta_pdf = item.get('ruta_pdf')
            no_encontrado = item.get('no_encontrado', False)
            
            # Si es no encontrado, crear registro sin PDF
            if no_encontrado or ruta_pdf is None:
                datos = {
                    'Numero': numero,
                    'CUFE': cufe,
                    'Estado': '⚠️ No registrado en DIAN',
                    'Ruta_PDF': '',
                    'Notas': 'Documento no encontrado en el portal DIAN'
                }
                with lock_excel:
                    datos_completos.append(datos)
                procesados += 1
                log(99, f"⚠️ #{numero} marcado como no encontrado", "WARN")
                continue
            
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
    """
    Ejecuta el sistema de descarga completo
    
    OPTIMIZACIONES v3.7.0:
    - Número de navegadores calculado dinámicamente
    - Cola unificada de trabajo y fallidos
    - Los navegadores toman CUFEs fallidos de otros navegadores
    - Limpieza completa al finalizar
    """
    global _contador_procesados, _total_cufes, _stop_signal, _navegadores_en_uso, _max_navegadores
    
    _contador_procesados = 0
    _total_cufes = len(cufes)
    _stop_signal.clear()
    _navegadores_en_uso = 0
    
    configurar_callbacks(callback_progreso, callback_mensaje)
    
    DIAN_URL = config['dian_url']
    CARPETA_PDFS = config['carpeta_pdfs']
    ARCHIVO_EXCEL = config['archivo_excel']
    MAX_REINTENTOS = config['max_reintentos']
    CARPETA_TEMP = config.get('carpeta_temp', None)
    
    # Calcular número óptimo de navegadores
    _max_navegadores = _calcular_max_navegadores(len(cufes), config['num_navegadores'])
    NUM_NAVEGADORES = _max_navegadores
    
    log(0, f"📊 Usando {NUM_NAVEGADORES} navegadores para {len(cufes)} CUFEs", "INFO")
    _notificar_mensaje(f"Preparando consulta de {len(cufes)} facturas...", "info")
    
    # Configurar carpeta para datos de Chrome
    if CARPETA_TEMP:
        chrome_temp = os.path.join(CARPETA_TEMP, "chrome_data")
        configurar_carpeta_chrome(chrome_temp)
    
    # Colas
    cola_trabajo = queue.Queue()
    cola_fallidos = queue.Queue()  # Cola para CUFEs que fallaron
    cola_pdfs = queue.Queue()
    cola_resultados = queue.Queue()
    
    lock_excel = threading.Lock()
    datos_completos = []
    
    # Llenar cola de trabajo
    for i, cufe in enumerate(cufes, 1):
        cola_trabajo.put((cufe, i, len(cufes), 1))  # (cufe, numero, total, intento)
    
    # Señales de fin para cada navegador
    for _ in range(NUM_NAVEGADORES):
        cola_trabajo.put(None)
    
    # Crear threads de descarga
    threads = []
    for i in range(1, NUM_NAVEGADORES + 1):
        _reservar_slot_navegador()
        t = threading.Thread(
            target=trabajador_descarga,
            args=(i, cola_trabajo, cola_fallidos, cola_pdfs, cola_resultados,
                  DIAN_URL, CARPETA_PDFS, MAX_REINTENTOS),
            daemon=True
        )
        threads.append(t)
    
    # Thread extractor
    t_extractor = threading.Thread(
        target=trabajador_extractor,
        args=(cola_pdfs, datos_completos, lock_excel),
        daemon=True
    )
    threads.append(t_extractor)
    
    tiempo_inicio = time.time()
    log(0, "🎬 Iniciando...", "OK")
    
    # Iniciar todos los threads
    for t in threads:
        t.start()
    
    # Esperar a que terminen los workers de descarga
    for t in threads[:-1]:  # Todos menos el extractor
        t.join()
    
    log(0, "✓ Descargas completadas", "OK")
    _notificar_mensaje("Consultas completadas", "success")
    
    # Procesar cualquier CUFE fallido restante
    while not cola_fallidos.empty():
        try:
            item = cola_fallidos.get_nowait()
            cufe, numero, total, intento = item
            resultado = {
                'numero': numero,
                'cufe': cufe,
                'estado': 'error',
                'pdf': None,
                'ruta_pdf': None,
                'mensaje': f'No procesado (intento {intento})',
                'intento': intento
            }
            cola_resultados.put(resultado)
        except:
            break
    
    # Finalizar extractor
    cola_pdfs.put(None)
    t_extractor.join()
    
    log(0, "✓ Extracción completada", "OK")
    
    # Generar Excel
    _notificar_mensaje("Generando reporte Excel...", "info")
    generar_excel_final(ARCHIVO_EXCEL, datos_completos)
    _notificar_mensaje("Proceso finalizado", "success")
    
    duracion = time.time() - tiempo_inicio
    
    # Recolectar resultados
    resultados = []
    while not cola_resultados.empty():
        try:
            resultados.append(cola_resultados.get_nowait())
        except:
            break
    
    resultados.sort(key=lambda x: x['numero'])
    
    # Limpiar navegadores y carpetas Chrome
    log(0, "🧹 Limpiando recursos...", "INFO")
    limpiar_navegadores()
    limpiar_carpetas_chrome()
    
    configurar_callbacks(None, None)
    
    return {
        'resultados': resultados,
        'datos_completos': datos_completos,
        'duracion': duracion,
        'num_navegadores': NUM_NAVEGADORES
    }