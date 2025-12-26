"""
═══════════════════════════════════════════════════════════════════════════
ORQUESTADOR - CUFE DIAN AUTOMATION
Coordina la ejecución paralela de navegadores, reintentos y extractor
v3.5.3 - Navegador de reintentos SIEMPRE LISTO (igual que backup v3.3)
═══════════════════════════════════════════════════════════════════════════
"""

import time
import threading
import queue
from utils import log
from core.descargador import inicializar_navegador, descargar_cufe
from core.extractor import extraer_datos_pdf
from core.excel_generator import generar_excel_final


def trabajador_descarga(nav_id: int, cola_trabajo: queue.Queue, cola_reintentos: queue.Queue,
                       cola_pdfs: queue.Queue, cola_resultados: queue.Queue,
                       navegadores_activos: list, dian_url: str, carpeta_pdfs: str,
                       max_reintentos: int):
    """
    Worker que descarga CUFEs en paralelo
    """
    page = None
    bypass = None
    
    try:
        page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
        
        if page is None:
            log(nav_id, "❌ No se pudo iniciar navegador", "ERROR")
            return
        
        navegadores_activos.append(page)
        
        while True:
            try:
                item = cola_trabajo.get(timeout=3)
                
                if item is None:
                    log(nav_id, "🏁 Fin", "INFO")
                    break
                
                cufe, numero, total = item
                
                resultado = descargar_cufe(
                    page, bypass, cufe, numero, total, nav_id,
                    carpeta_pdfs, intento=1, max_reintentos=max_reintentos
                )
                
                if resultado['estado'] == 'retry':
                    log(nav_id, f"⚠️ Falló, enviando a reintentos...", "RETRY")
                    cola_reintentos.put((cufe, numero, total))
                else:
                    cola_resultados.put(resultado)
                    
                    if resultado['estado'] == 'exitoso' and resultado['ruta_pdf']:
                        cola_pdfs.put({
                            'numero': numero,
                            'cufe': cufe,
                            'ruta_pdf': resultado['ruta_pdf']
                        })
                        log(nav_id, "→ PDF enviado a extractor", "DEBUG")
                
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
    Worker dedicado a procesar reintentos - IGUAL QUE BACKUP v3.3
    
    IMPORTANTE:
    - El navegador se inicia INMEDIATAMENTE y queda listo
    - Procesa reintentos TAN PRONTO como llegan a la cola
    - No espera a que los principales terminen
    """
    log(nav_id, "🔄 Procesador de reintentos iniciado", "RETRY")
    
    # INICIAR NAVEGADOR INMEDIATAMENTE - igual que backup v3.3
    page, bypass = inicializar_navegador(nav_id, carpeta_pdfs, dian_url)
    
    if page is None:
        log(nav_id, "❌ No se pudo iniciar navegador de reintentos", "ERROR")
        return
    
    navegadores_activos.append(page)
    procesados = 0
    
    # Ciclo principal - espera y procesa reintentos
    while True:
        try:
            # Esperar item con timeout de 10s (igual que backup v3.3)
            item = cola_reintentos.get(timeout=10)
            
            if item is None:
                log(nav_id, "🏁 Fin reintentos", "RETRY")
                break
            
            cufe, numero, total = item
            
            # Tracking de intentos
            with lock_reintentos:
                intento_actual = intentos_por_cufe.get(cufe, 1) + 1
                intentos_por_cufe[cufe] = intento_actual
            
            log(nav_id, f"🔄 Reintentando CUFE #{numero} (intento {intento_actual}/{max_reintentos})", "RETRY")
            
            # Reintentar descarga
            resultado = descargar_cufe(
                page, bypass, cufe, numero, total, nav_id,
                carpeta_pdfs, intento=intento_actual, max_reintentos=max_reintentos
            )
            
            resultado['intento'] = intento_actual
            
            # Si falló de nuevo y puede reintentar
            if resultado['estado'] == 'retry' and intento_actual < max_reintentos:
                log(nav_id, f"⚠️ Falló de nuevo, reintentando...", "RETRY")
                cola_reintentos.put((cufe, numero, total))
            else:
                # Éxito o fallo definitivo
                if resultado['estado'] == 'retry':
                    resultado['estado'] = 'error'
                
                cola_resultados.put(resultado)
                
                if resultado['estado'] == 'exitoso' and resultado['ruta_pdf']:
                    cola_pdfs.put({
                        'numero': numero,
                        'cufe': cufe,
                        'ruta_pdf': resultado['ruta_pdf']
                    })
                    log(nav_id, "✅ REINTENTO EXITOSO", "OK")
            
            procesados += 1
            time.sleep(3)
            
        except queue.Empty:
            # Timeout - seguir esperando (no salir todavía)
            continue
        except Exception as e:
            log(nav_id, f"Error reintentos: {e}", "ERROR")
            break
    
    # Mostrar estadísticas
    if procesados > 0:
        log(nav_id, f"✓ Procesados {procesados} reintentos", "RETRY")
    
    # Cerrar navegador
    try:
        page.quit()
        if page in navegadores_activos:
            navegadores_activos.remove(page)
        log(nav_id, "Navegador de reintentos cerrado", "RETRY")
    except:
        pass


def trabajador_extractor(cola_pdfs: queue.Queue, datos_completos: list, 
                        lock_excel: threading.Lock):
    """
    Worker que extrae datos de PDFs
    """
    log(99, "🔍 Extractor iniciado", "OK")
    procesados = 0
    
    while True:
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


def ejecutar_sistema(cufes: list, config: dict):
    """
    Función principal que ejecuta todo el sistema
    """
    # Configuración
    DIAN_URL = config['dian_url']
    CARPETA_PDFS = config['carpeta_pdfs']
    ARCHIVO_EXCEL = config['archivo_excel']
    NUM_NAVEGADORES = min(len(cufes), config['num_navegadores'])
    MAX_REINTENTOS = config['max_reintentos']
    
    # Colas
    cola_trabajo = queue.Queue()
    cola_reintentos = queue.Queue()
    cola_pdfs = queue.Queue()
    cola_resultados = queue.Queue()
    
    # Locks
    lock_excel = threading.Lock()
    lock_reintentos = threading.Lock()
    
    # Estado
    navegadores_activos = []
    datos_completos = []
    intentos_por_cufe = {}
    
    # Llenar cola de trabajo
    for i, cufe in enumerate(cufes, 1):
        cola_trabajo.put((cufe, i, len(cufes)))
    
    for _ in range(NUM_NAVEGADORES):
        cola_trabajo.put(None)
    
    # Crear threads
    threads = []
    
    # Navegadores principales
    for i in range(1, NUM_NAVEGADORES + 1):
        t = threading.Thread(
            target=trabajador_descarga,
            args=(i, cola_trabajo, cola_reintentos, cola_pdfs, cola_resultados,
                  navegadores_activos, DIAN_URL, CARPETA_PDFS, MAX_REINTENTOS)
        )
        threads.append(t)
    
    # Navegador de reintentos - SIEMPRE LISTO
    t_reintentos = threading.Thread(
        target=procesador_reintentos,
        args=(98, cola_reintentos, cola_pdfs, cola_resultados, navegadores_activos,
              DIAN_URL, CARPETA_PDFS, MAX_REINTENTOS, intentos_por_cufe, lock_reintentos)
    )
    threads.append(t_reintentos)
    
    # Extractor
    t_extractor = threading.Thread(
        target=trabajador_extractor,
        args=(cola_pdfs, datos_completos, lock_excel)
    )
    threads.append(t_extractor)
    
    # Iniciar todos
    tiempo_inicio = time.time()
    log(0, "🎬 Iniciando...", "OK")
    
    for t in threads:
        t.start()
    
    # Esperar navegadores principales
    for t in threads[:NUM_NAVEGADORES]:
        t.join()
    
    log(0, "✓ Descargas principales completadas", "OK")
    
    # Señal de parada para reintentos
    cola_reintentos.put(None)
    t_reintentos.join()
    
    log(0, "✓ Reintentos completados", "OK")
    
    # Parar extractor
    cola_pdfs.put(None)
    t_extractor.join()
    
    log(0, "✓ Extracción completada", "OK")
    
    # Generar Excel
    generar_excel_final(ARCHIVO_EXCEL, datos_completos)
    
    duracion = time.time() - tiempo_inicio
    
    # Recolectar resultados
    resultados = []
    while not cola_resultados.empty():
        resultados.append(cola_resultados.get())
            
    resultados.sort(key=lambda x: x['numero'])
    
    return {
        'resultados': resultados,
        'datos_completos': datos_completos,
        'duracion': duracion,
        'num_navegadores': NUM_NAVEGADORES
    }