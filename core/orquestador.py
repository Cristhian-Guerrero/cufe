"""
═══════════════════════════════════════════════════════════════════════════
ORQUESTADOR - CUFE DIAN AUTOMATION (LINUX/FEDORA FINAL)
v3.7.5 - Conecta eventos, abre archivo automático y gestiona memoria
═══════════════════════════════════════════════════════════════════════════
"""

import time
import threading
import queue
import os
import subprocess # Necesario para abrir el archivo en Linux
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
    """Calcula el número óptimo de navegadores"""
    import platform
    optimo = min(num_cufes, config_max)
    if platform.system() == "Windows":
        optimo = min(optimo, 8)
    optimo = max(optimo, 2)
    return optimo


def trabajador_descarga(nav_id: int, cola_trabajo: queue.Queue, cola_fallidos: queue.Queue,
                       cola_pdfs: queue.Queue, cola_resultados: queue.Queue,
                       dian_url: str, carpeta_pdfs: str, max_reintentos: int):
    """
    Worker de descarga con soporte para eventos
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
                break
            
            try:
                # Prioridad a reintentos
                item = None
                try:
                    item = cola_fallidos.get_nowait()
                    if len(item) == 5:
                        cufe, numero, total, intento, nav_anterior = item
                        if nav_anterior == nav_id: # Evitar loop mismo nav
                            cola_fallidos.put(item)
                            item = None
                except queue.Empty:
                    pass
                
                # Cola normal
                if item is None:
                    try:
                        item = cola_trabajo.get(timeout=2)
                    except queue.Empty:
                        continue
                
                if item is None: # Señal de fin
                    break
                
                # Desempaquetar
                if len(item) == 5:
                    cufe, numero, total, intento, nav_anterior = item
                elif len(item) == 4:
                    cufe, numero, total, intento = item
                else:
                    cufe, numero, total = item
                    intento = 1
                
                _notificar_mensaje(f"Consultando factura {numero} de {total}...", "info")
                
                # DESCARGAR
                resultado = descargar_cufe(
                    page, bypass, cufe, numero, total, nav_id,
                    carpeta_pdfs, intento=intento, max_reintentos=max_reintentos
                )
                
                if resultado['estado'] == 'retry':
                    fallos_consecutivos += 1
                    if intento < max_reintentos:
                        cola_fallidos.put((cufe, numero, total, intento + 1, nav_id))
                        _notificar_mensaje(f"Reintentando factura {numero}...", "warning")
                        
                        if fallos_consecutivos >= MAX_FALLOS_ANTES_REINICIAR:
                            cerrar_navegador(nav_id)
                            time.sleep(2)
                            page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
                            if page is None: break
                            fallos_consecutivos = 0
                    else:
                        resultado['estado'] = 'error'
                        resultado['mensaje'] = f"Falló tras {max_reintentos} intentos"
                        cola_resultados.put(resultado)
                        _notificar_progreso()
                else:
                    fallos_consecutivos = 0
                    cola_resultados.put(resultado)
                    _notificar_progreso()
                    
                    if resultado['estado'] == 'exitoso' and resultado['ruta_pdf']:
                        # === AQUÍ PASAMOS LOS EVENTOS AL EXTRACTOR ===
                        cola_pdfs.put({
                            'numero': numero,
                            'cufe': cufe,
                            'ruta_pdf': resultado['ruta_pdf'],
                            'eventos': resultado.get('eventos', '') # <--- CLAVE NUEVA
                        })
                        _notificar_mensaje(f"Factura {numero} descargada", "success")
                    elif resultado['estado'] == 'no_encontrado':
                        cola_pdfs.put({
                            'numero': numero,
                            'cufe': cufe,
                            'ruta_pdf': None,
                            'no_encontrado': True
                        })
                
                time.sleep(1)
                
            except Exception as e:
                log(nav_id, f"Error worker: {e}", "ERROR")
                fallos_consecutivos += 1
    
    except Exception as e:
        log(nav_id, f"Error iniciando: {e}", "ERROR")
    
    finally:
        cerrar_navegador(nav_id)
        _liberar_slot_navegador()


def trabajador_extractor(cola_pdfs: queue.Queue, datos_completos: list, 
                        lock_excel: threading.Lock):
    """Extractor que recibe PDFs y Eventos"""
    log(99, "🔍 Extractor iniciado", "OK")
    
    while True:
        if _stop_signal.is_set():
            break
        
        try:
            item = cola_pdfs.get(timeout=5)
            if item is None: break
            
            numero = item['numero']
            cufe = item['cufe']
            ruta_pdf = item.get('ruta_pdf')
            no_encontrado = item.get('no_encontrado', False)
            eventos = item.get('eventos', '') # Recibimos eventos
            
            if no_encontrado or ruta_pdf is None:
                datos = {
                    'Numero': numero,
                    'CUFE': cufe,
                    'Estado': '⚠️ No registrado en DIAN',
                    'Ruta_PDF': '',
                    'Notas': 'Documento no encontrado'
                }
                with lock_excel:
                    datos_completos.append(datos)
                continue
            
            log(99, f"📄 Extrayendo #{numero}...", "INFO")
            
            # Extraer datos del PDF
            datos = extraer_datos_pdf(ruta_pdf, cufe, numero)
            
            # === INYECTAR EVENTOS EN EL DICCIONARIO ===
            datos['Eventos'] = eventos
            
            with lock_excel:
                datos_completos.append(datos)
            
            log(99, f"✓ Procesado #{numero}", "OK")
            
        except queue.Empty:
            time.sleep(1)
        except Exception as e:
            log(99, f"Error extractor: {e}", "ERROR")


def ejecutar_sistema(cufes: list, config: dict, callback_progreso=None, callback_mensaje=None):
    """
    Punto de entrada principal
    """
    global _contador_procesados, _total_cufes, _stop_signal, _navegadores_en_uso
    
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
    
    NUM_NAVEGADORES = _calcular_max_navegadores(len(cufes), config['num_navegadores'])
    
    log(0, f"🚀 Iniciando con {NUM_NAVEGADORES} navegadores", "INFO")
    
    if CARPETA_TEMP:
        configurar_carpeta_chrome(os.path.join(CARPETA_TEMP, "chrome_data"))
    
    cola_trabajo = queue.Queue()
    cola_fallidos = queue.Queue()
    cola_pdfs = queue.Queue()
    cola_resultados = queue.Queue()
    lock_excel = threading.Lock()
    datos_completos = []
    
    for i, cufe in enumerate(cufes, 1):
        cola_trabajo.put((cufe, i, len(cufes), 1))
    
    for _ in range(NUM_NAVEGADORES):
        cola_trabajo.put(None)
    
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
    
    t_extractor = threading.Thread(
        target=trabajador_extractor,
        args=(cola_pdfs, datos_completos, lock_excel),
        daemon=True
    )
    threads.append(t_extractor)
    
    for t in threads:
        t.start()
    
    for t in threads[:-1]:
        t.join()
        
    # Procesar remanentes fallidos
    while not cola_fallidos.empty():
        try:
            item = cola_fallidos.get_nowait()
            cufe = item[0]; numero = item[1]; intento = item[3]
            cola_resultados.put({
                'numero': numero, 'cufe': cufe, 'estado': 'error',
                'mensaje': f'No procesado (intento {intento})'
            })
        except: break
    
    cola_pdfs.put(None)
    t_extractor.join()
    
    # Generar Excel
    _notificar_mensaje("Generando Excel...", "info")
    generar_excel_final(ARCHIVO_EXCEL, datos_completos)
    _notificar_mensaje("Proceso finalizado", "success")
    
    # === ABRIR ARCHIVO AUTOMÁTICAMENTE (FEDORA/LINUX) ===
    try:
        import platform
        sistema = platform.system()
        log(0, f"📂 Abriendo reporte: {ARCHIVO_EXCEL}", "INFO")
    
        if sistema == "Windows":
            os.startfile(ARCHIVO_EXCEL)
        elif sistema == "Darwin":  # macOS
            subprocess.run(['open', ARCHIVO_EXCEL], check=False)
        else:  # Linux
            subprocess.run(['xdg-open', ARCHIVO_EXCEL], check=False)
    except Exception as e:
        log(0, f"No se pudo abrir automático: {e}", "WARN")
    # ====================================================
    
    duracion = 0 # Simplificado
    resultados = []
    while not cola_resultados.empty():
        resultados.append(cola_resultados.get())
    resultados.sort(key=lambda x: x['numero'])
    
    limpiar_navegadores()
    limpiar_carpetas_chrome()
    
    return {
        'resultados': resultados,
        'datos_completos': datos_completos,
        'duracion': duracion,
        'num_navegadores': NUM_NAVEGADORES
    }