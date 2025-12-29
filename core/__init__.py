"""
Módulo core - Lógica principal de descarga y procesamiento
v3.7.0 - Actualizado para nueva arquitectura
"""

from .extractor import ExtractorPDF, extraer_datos_pdf
from .excel_generator import GeneradorExcel, generar_excel_final
from .validador import ValidadorCUFE, cargar_cufes

__all__ = [
    'ExtractorPDF', 
    'extraer_datos_pdf',
    'GeneradorExcel',
    'generar_excel_final',
    'ValidadorCUFE',
    'cargar_cufes'
]

from core.descargador import (
    inicializar_navegador,
    descargar_cufe,
    detectar_pdf,
    generar_nombre_unico,
    cerrar_navegador,
    limpiar_navegadores,
    limpiar_carpetas_chrome
)

from core.orquestador import (
    ejecutar_sistema,
    trabajador_descarga,
    trabajador_extractor
)