"""
═══════════════════════════════════════════════════════════════════════════
GENERADOR DE EXCEL - CUFE DIAN AUTOMATION
Genera Excel profesional con formato, hipervínculos y filtros
═══════════════════════════════════════════════════════════════════════════
"""

import os
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from utils import log


class GeneradorExcel:
    """
    Generador de archivos Excel con formato profesional
    
    Características:
    - Encabezados con formato
    - Filas alternadas (cebra)
    - Columnas con anchos personalizados
    - Hipervínculos a PDFs
    - Formato de moneda
    - Filtros automáticos
    """
    
    # Orden de columnas en el Excel
    COLUMNAS_ORDEN = [
        'Numero', 'Estado', 'Numero_Factura', 'Prefijo', 'Folio',
        'Fecha_Emision', 'Fecha_Vencimiento',
        'Emisor_RazonSocial', 'Emisor_NIT', 'Emisor_Ciudad', 'Emisor_Departamento',
        'Emisor_Direccion', 'Emisor_Telefono', 'Emisor_Email',
        'Receptor_RazonSocial', 'Receptor_NIT', 'Receptor_Ciudad', 'Receptor_Departamento',
        'Receptor_Direccion', 'Receptor_Email',
        'Subtotal', 'IVA', 'Total_Factura',
        'Forma_Pago', 'Medio_Pago', 'Numero_Autorizacion',
        'CUFE', 'Ruta_PDF', 'Notas'
    ]
    
    # Anchos personalizados por columna
    ANCHOS_COLUMNAS = {
        'A': 8, 'B': 12, 'C': 18, 'D': 10, 'E': 10,
        'F': 14, 'G': 14, 'H': 35, 'I': 16, 'J': 20,
        'K': 18, 'L': 35, 'M': 16, 'N': 30, 'O': 35,
        'P': 16, 'Q': 20, 'R': 18, 'S': 35, 'T': 30,
        'U': 15, 'V': 15, 'W': 15, 'X': 18, 'Y': 18,
        'Z': 18, 'AA': 70, 'AB': 15, 'AC': 50
    }
    
    def __init__(self, nombre_archivo):
        """
        Inicializa el generador
        
        Args:
            nombre_archivo: Nombre del archivo Excel a generar
        """
        self.nombre_archivo = nombre_archivo
    
    def generar(self, datos_completos):
        """
        Genera el Excel completo con datos y formato
        
        Args:
            datos_completos: Lista de diccionarios con datos extraídos
            
        Returns:
            bool: True si se generó correctamente
        """
        if not datos_completos:
            log(98, "❌ No hay datos", "ERROR")
            return False
        
        try:
            # Ordenar por número
            datos_ordenados = sorted(datos_completos, key=lambda x: x.get('Numero', 999))
            
            # Crear DataFrame
            df = pd.DataFrame(datos_ordenados)
            
            # Reordenar columnas
            df = df[self.COLUMNAS_ORDEN]
            
            # Guardar Excel básico
            df.to_excel(self.nombre_archivo, index=False, sheet_name='Facturas')
            log(98, "✓ Datos guardados", "OK")
            
            # Aplicar formato profesional
            self._aplicar_formato(datos_completos)
            log(98, "✅ Excel profesional generado", "OK")
            
            return True
            
        except Exception as e:
            log(98, f"❌ Error generando Excel: {e}", "ERROR")
            return False
    
    def _aplicar_formato(self, datos_completos):
        """
        Aplica formato profesional al Excel
        
        Args:
            datos_completos: Datos originales (para hipervínculos)
        """
        try:
            wb = load_workbook(self.nombre_archivo)
            ws = wb.active
            
            # Estilos
            fill_header = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            font_header = Font(bold=True, color="FFFFFF", size=12, name='Calibri')
            align_header = Alignment(horizontal='center', vertical='center', wrap_text=True)
            
            borde_grueso = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            fill_par = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            fill_impar = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
            
            align_centro = Alignment(horizontal='center', vertical='center')
            align_izquierda = Alignment(horizontal='left', vertical='center')
            align_derecha = Alignment(horizontal='right', vertical='center')
            
            # Formatear encabezados
            for cell in ws[1]:
                cell.fill = fill_header
                cell.font = font_header
                cell.alignment = align_header
                cell.border = borde_grueso
            
            # Anchos de columnas
            for col, ancho in self.ANCHOS_COLUMNAS.items():
                ws.column_dimensions[col].width = ancho
            
            # Encontrar columnas especiales
            col_estado = None
            col_pdf = None
            col_subtotal = None
            col_iva = None
            col_total = None
            
            for idx, cell in enumerate(ws[1], 1):
                if cell.value == 'Estado':
                    col_estado = idx
                elif cell.value == 'Ruta_PDF':
                    col_pdf = idx
                elif cell.value == 'Subtotal':
                    col_subtotal = idx
                elif cell.value == 'IVA':
                    col_iva = idx
                elif cell.value == 'Total_Factura':
                    col_total = idx
            
            # Formatear filas de datos
            for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
                fill = fill_par if row_idx % 2 == 0 else fill_impar
                
                for cell_idx, cell in enumerate(row, 1):
                    cell.border = borde_grueso
                    cell.fill = fill
                    
                    # Formato según columna
                    if cell_idx == 1:  # Número
                        cell.alignment = align_centro
                        cell.font = Font(bold=True, size=11)
                    elif cell_idx == col_estado:  # Estado
                        cell.alignment = align_centro
                        cell.font = Font(size=11)
                    elif cell_idx in [col_subtotal, col_iva, col_total]:  # Valores monetarios
                        cell.alignment = align_derecha
                        cell.number_format = '$#,##0.00'
                        cell.font = Font(bold=True if cell_idx == col_total else False, size=11)
                    else:
                        cell.alignment = align_izquierda
                    
                    # Hipervínculo a PDF
                    if cell_idx == col_pdf:
                        for dato in datos_completos:
                            if dato.get('Numero') == row_idx - 1:
                                ruta_real = dato.get('Ruta_PDF', '')
                                if ruta_real and os.path.exists(ruta_real):
                                    cell.hyperlink = f"file:///{ruta_real.replace(os.sep, '/')}"
                                    cell.value = "📄 Ver PDF"
                                    cell.font = Font(color="0000FF", underline="single", size=11)
                                    cell.alignment = align_centro
                                break
            
            # Congelar primera fila
            ws.freeze_panes = 'A2'
            
            # Altura de filas
            ws.row_dimensions[1].height = 30
            for row_idx in range(2, ws.max_row + 1):
                ws.row_dimensions[row_idx].height = 20
            
            # Filtros automáticos
            ws.auto_filter.ref = ws.dimensions
            
            # Guardar
            wb.save(self.nombre_archivo)
            log(98, "✓ Formato aplicado", "OK")
            
        except Exception as e:
            log(98, f"Error formato: {e}", "ERROR")


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIÓN DE CONVENIENCIA (compatibilidad con código original)
# ═══════════════════════════════════════════════════════════════════════════

def generar_excel_final(nombre_archivo, datos_completos):
    """
    Función wrapper para mantener compatibilidad con código original
    
    Args:
        nombre_archivo: Nombre del archivo Excel
        datos_completos: Lista de datos extraídos
        
    Returns:
        bool: True si se generó correctamente
    """
    generador = GeneradorExcel(nombre_archivo)
    return generador.generar(datos_completos)


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 PROBANDO GENERADOR DE EXCEL")
    print("="*70 + "\n")
    
    # Datos de prueba
    datos_test = [
        {
            'Numero': 1,
            'Estado': '✅ Procesado',
            'Numero_Factura': 'FE-001',
            'Prefijo': 'FE',
            'Folio': '001',
            'Fecha_Emision': '01/01/2025',
            'Fecha_Vencimiento': '31/01/2025',
            'Emisor_RazonSocial': 'Empresa Test SAS',
            'Emisor_NIT': '900123456-1',
            'Emisor_Ciudad': 'Bogotá',
            'Emisor_Departamento': 'Cundinamarca',
            'Emisor_Direccion': 'Calle 123 #45-67',
            'Emisor_Telefono': '3001234567',
            'Emisor_Email': 'test@empresa.com',
            'Receptor_RazonSocial': 'Cliente Test',
            'Receptor_NIT': '123456789',
            'Receptor_Ciudad': 'Medellín',
            'Receptor_Departamento': 'Antioquia',
            'Receptor_Direccion': 'Carrera 10 #20-30',
            'Receptor_Email': 'cliente@test.com',
            'Subtotal': '100000',
            'IVA': '19000',
            'Total_Factura': '119000',
            'Forma_Pago': 'Contado',
            'Medio_Pago': 'Efectivo',
            'Numero_Autorizacion': '123456',
            'CUFE': 'abc123def456...',
            'Ruta_PDF': '/tmp/test.pdf',
            'Notas': ''
        }
    ]
    
    # Generar Excel de prueba
    generador = GeneradorExcel('Test_Excel.xlsx')
    if generador.generar(datos_test):
        print("✅ Excel de prueba generado: Test_Excel.xlsx")
    else:
        print("❌ Error generando Excel de prueba")
    
    print("\n" + "="*70 + "\n")
