#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
CUFE DIAN AUTOMATION - MAIN
Sistema de descarga masiva de facturas electrónicas desde DIAN
v3.5.0 - Arquitectura modular completa
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import json
import atexit
from datetime import datetime

# === MÓDULOS PROPIOS ===
from config import cargar_settings
from utils import log, obtener_logger
from core.validador import cargar_cufes
from core.orquestador import ejecutar_sistema


# === CONFIGURACIÓN GLOBAL ===
settings = cargar_settings()
ARCHIVO_MAPPING = settings.archivo_mapping
mapping_cufes = {}
navegadores_activos = []


def limpiar_al_salir():
    """Limpia navegadores al salir"""
    log(0, "🧹 Limpiando...", "WARN")
    for page in navegadores_activos:
        try:
            page.quit()
        except:
            pass


def guardar_mapping():
    """Guarda mapping JSON de CUFEs a PDFs"""
    try:
        with open(ARCHIVO_MAPPING, 'w', encoding='utf-8') as f:
            json.dump(mapping_cufes, f, indent=2, ensure_ascii=False)
    except:
        pass


def guardar_progreso_parcial(datos_completos, resultados):
    """Guarda progreso parcial cuando se interrumpe (Ctrl+C)"""
    log(0, "\n💾 Guardando progreso parcial...", "WARN")
    
    try:
        if datos_completos:
            from core.excel_generator import generar_excel_final
            archivo_parcial = f"Facturas_Parcial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            generar_excel_final(archivo_parcial, datos_completos)
            log(0, f"✅ Excel parcial guardado: {archivo_parcial}", "OK")
            log(0, f"📊 {len(datos_completos)} facturas procesadas", "INFO")
        else:
            log(0, "⚠️  No hay datos para guardar", "WARN")
        
        guardar_mapping()
        
        if resultados:
            exitosos = [r for r in resultados if r['estado'] == 'exitoso']
            errores = [r for r in resultados if r['estado'] == 'error']
            log(0, f"✅ Completados: {len(exitosos)}", "OK")
            log(0, f"❌ Con error: {len(errores)}", "ERROR")
        
    except Exception as e:
        log(0, f"❌ Error guardando progreso: {e}", "ERROR")


atexit.register(limpiar_al_salir)


def main():
    """Función principal del sistema"""
    import sys
    
    # Configurar logging a archivo
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archivo_log = f'logs/ejecucion_{timestamp}.log'
    os.makedirs('logs', exist_ok=True)
    
    # Configurar el logger global
    logger_global = obtener_logger()
    logger_global.configurar_archivo(archivo_log)
    log(0, f"📄 Log guardándose en: {archivo_log}", "INFO")
    
    # Permitir archivo como argumento
    archivo_cufes = sys.argv[1] if len(sys.argv) > 1 else 'cufes_test.txt'
    
    print("\n" + "="*70)
    print("🚀 SISTEMA ULTRA OPTIMIZADO - NAVEGADORES DINÁMICOS + REINTENTOS")
    print("="*70)
    print()
    
    # Cargar y validar CUFEs
    cufes = cargar_cufes(archivo_cufes)
    
    if not cufes:
        log(0, "❌ No hay CUFEs válidos para procesar", "CRIT")
        return
    
    # Configuración para el orquestador
    config = {
        'dian_url': settings.dian_url,
        'carpeta_pdfs': settings.carpeta_pdfs,
        'archivo_excel': settings.archivo_excel,
        'num_navegadores': settings.num_navegadores,
        'max_reintentos': settings.max_reintentos
    }
    
    # Ajuste dinámico de navegadores
    num_navegadores = min(len(cufes), config['num_navegadores'])
    
    log(0, f"📋 {len(cufes)} CUFEs", "INFO")
    log(0, f"🚀 {num_navegadores} navegadores paralelos", "INFO")
    log(0, f"🔄 {config['max_reintentos']} reintentos automáticos", "INFO")
    log(0, f"📁 {config['carpeta_pdfs']}/", "INFO")
    log(0, f"📊 {config['archivo_excel']}", "INFO")
    print()
    
    # Ejecutar sistema
    resultado = ejecutar_sistema(cufes, config)
    
    # Guardar mapping
    guardar_mapping()
    
    # Mostrar resultados
    print("\n" + "="*70)
    print("📊 RESULTADOS FINALES")
    print("="*70)
    
    resultados = resultado['resultados']
    datos_completos = resultado['datos_completos']
    duracion = resultado['duracion']
    num_navegadores = resultado['num_navegadores']
    
    exitosos = [r for r in resultados if r['estado'] == 'exitoso']
    no_encontrados = [r for r in resultados if r['estado'] == 'no_encontrado']
    errores = [r for r in resultados if r['estado'] == 'error']
    
    log(0, f"✅ Exitosos: {len(exitosos)}/{len(cufes)}", "OK")
    log(0, f"⚠️ No encontrados: {len(no_encontrados)}", "WARN")
    log(0, f"❌ Errores: {len(errores)}", "ERROR")
    log(0, f"⏱️ Tiempo: {duracion:.1f}s ({duracion/60:.1f}min)", "INFO")
    log(0, f"📊 Excel: {config['archivo_excel']}", "EXCEL")
    log(0, f"📂 PDFs: {config['carpeta_pdfs']}/", "INFO")
    log(0, f"✨ {len(datos_completos)} registros en Excel", "OK")
    
    # Estadísticas de reintentos
    total_reintentos = sum(1 for r in resultados if r.get('intento', 1) > 1)
    if total_reintentos > 0:
        log(0, f"🔄 {total_reintentos} CUFEs necesitaron reintentos", "RETRY")
    
    # Proyección
    if exitosos:
        promedio = duracion / len(cufes)
        estimacion_100 = (100 * promedio) / num_navegadores / 60
        log(0, f"📈 Estimación 100 CUFEs: ~{estimacion_100:.1f} min", "INFO")
    
    if errores:
        print("\n❌ ERRORES DEFINITIVOS:")
        for r in errores:
            print(f"  CUFE #{r['numero']}: {r['mensaje']} (intentos: {r.get('intento', 1)})")
    
    print("\n✅ Proceso completado\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log(0, "\n⚠️ Interrumpido por usuario (Ctrl+C)", "WARN")
        # Aquí se podría llamar a guardar_progreso_parcial si tuviéramos acceso a las variables
        log(0, "💾 Limpiando...", "INFO")
        limpiar_al_salir()
    except Exception as e:
        log(0, f"\n❌ Error: {e}", "ERROR")
        limpiar_al_salir()
