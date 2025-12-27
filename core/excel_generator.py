"""
═══════════════════════════════════════════════════════════════════════════
GENERADOR DE EXCEL - CUFE DIAN AUTOMATION (ACCOUNTING CLEAN)
v6.0 - Eliminadas columnas basura de nombres divididos
═══════════════════════════════════════════════════════════════════════════
"""

import os
import pandas as pd
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from utils import log

class GeneradorExcel:
    
    # ESTRUCTURA DEFINITIVA Y SIMPLE
    COLUMNAS_DEF = [
        # GRUPO 0: CONTROL
        ('Numero', 'N°', 6, 0), 
        ('Estado', 'Estado', 12, 0),
        ('Numero_Factura', 'Factura N°', 15, 0),
        
        # GRUPO 1: DATOS DEL DOCUMENTO
        ('CUFE', 'CUFE', 25, 1), 
        ('Fecha_Emision', 'Emisión', 12, 1), 
        ('Fecha_Vencimiento', 'Vencimiento', 12, 1), 
        ('Tipo_Operacion', 'Tipo Operación', 18, 1), 
        ('Forma_Pago', 'Forma Pago', 15, 1), 
        ('Medio_Pago', 'Medio Pago', 20, 1), 
        
        # GRUPO 2: EMISOR
        ('Emisor_RazonSocial', 'Razón Social Vendedor', 35, 2), 
        ('Emisor_NIT', 'NIT Vendedor', 15, 2),
        ('Emisor_Departamento', 'Depto.', 15, 2), 
        ('Emisor_Municipio', 'Ciudad', 15, 2), 
        
        # GRUPO 3: ADQUIRIENTE (CLIENTE) - SIMPLIFICADO
        ('Adq_Tipo', 'Tipo Pers.', 12, 3), 
        ('Adq_NumeroDocumento', 'NIT / CC Cliente', 15, 3), 
        ('Adq_RazonSocial', 'RAZÓN SOCIAL / NOMBRE (LEGAL)', 40, 3), # EL CAMPO IMPORTANTE
        ('Adq_NombreComercial', 'Nombre Comercial / Establecimiento', 35, 3), # EL CAMPO SECUNDARIO
        ('Adq_Departamento', 'Depto.', 15, 3), 
        ('Adq_Municipio', 'Ciudad', 15, 3), 
        ('Adq_Direccion', 'Dirección', 30, 3), 
        ('Adq_Correo', 'Email', 25, 3),
        
        # GRUPO 4: FINANCIERO
        ('Subtotal', 'Subtotal', 16, 4), 
        ('Total_Bruto', 'Total Bruto', 16, 4), 
        ('IVA', 'IVA', 14, 4), 
        ('INC', 'INC', 14, 4), 
        ('Bolsas', 'Bolsas', 12, 4),
        ('Total_Factura', 'TOTAL A PAGAR', 18, 4),
        ('Anticipos', 'Anticipos', 14, 4), 
        ('Rete_Fuente', 'ReteFuente', 14, 4), 
        ('Rete_IVA', 'ReteIVA', 14, 4), 
        ('Rete_ICA', 'ReteICA', 14, 4),
        
        # GRUPO 5: GESTIÓN
        ('Ruta_PDF', 'Soporte', 12, 5), 
        ('Notas', 'Observaciones', 30, 5)
    ]

    GRUPOS_INFO = {
        0: {'titulo': 'CONTROL', 'color': '404040', 'texto': 'FFFFFF'},
        1: {'titulo': 'DATOS DEL DOCUMENTO', 'color': '1F4E78', 'texto': 'FFFFFF'},
        2: {'titulo': 'DATOS DEL EMISOR', 'color': '375623', 'texto': 'FFFFFF'},
        3: {'titulo': 'DATOS DEL CLIENTE', 'color': '833C0C', 'texto': 'FFFFFF'},
        4: {'titulo': 'DETALLE FINANCIERO', 'color': '5B3151', 'texto': 'FFFFFF'},
        5: {'titulo': 'ADJUNTOS', 'color': '000000', 'texto': 'FFFFFF'}
    }

    def __init__(self, nombre_archivo):
        self.nombre_archivo = nombre_archivo
        self.fila_inicio_datos = 7 

    def generar(self, datos_completos):
        if not datos_completos: return False
        try:
            datos_ordenados = sorted(datos_completos, key=lambda x: x.get('Numero', 999))
            claves_columnas = [col[0] for col in self.COLUMNAS_DEF]
            df = pd.DataFrame(datos_ordenados)
            for clave in claves_columnas:
                if clave not in df.columns: df[clave] = ""
            df = df[claves_columnas]
            
            with pd.ExcelWriter(self.nombre_archivo, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, header=False, sheet_name='Reporte DIAN', startrow=self.fila_inicio_datos-1)
            
            self._aplicar_diseno_premium(df)
            return True
        except Exception as e:
            log(98, f"❌ Error generando Excel: {e}", "ERROR")
            return False
    
    def _aplicar_diseno_premium(self, df):
        try:
            wb = load_workbook(self.nombre_archivo)
            ws = wb.active
            
            # ESTILOS
            font_dashboard_lbl = Font(name='Segoe UI', size=9, color="666666")
            font_dashboard_val = Font(name='Segoe UI', size=14, bold=True, color="1F4E78")
            font_grupo = Font(name='Segoe UI', size=10, bold=True, color="FFFFFF")
            font_header = Font(name='Segoe UI', size=9, bold=True, color="FFFFFF")
            font_data = Font(name='Segoe UI', size=9)
            
            border_thin = Side(style='thin', color="BFBFBF")
            border_med = Side(style='medium', color="FFFFFF")
            borde_cuadro = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)
            
            align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)

            # DASHBOARD MINIMALISTA
            ws['B2'] = "REPORTE CONTABLE DE FACTURAS"
            ws['B2'].font = Font(name='Segoe UI', size=16, bold=True, color="404040")
            
            ws['B3'] = "TOTAL DOCUMENTOS"
            ws['B3'].font = font_dashboard_lbl
            ws['B3'].alignment = align_center
            ws['B4'] = len(df)
            ws['B4'].font = font_dashboard_val
            ws['B4'].alignment = align_center
            ws['B4'].border = Border(bottom=Side(style='thick', color="1F4E78"))
            
            ws['D3'] = "FECHA GENERACIÓN"
            ws['D3'].font = font_dashboard_lbl
            ws['D3'].alignment = align_center
            ws['D4'] = datetime.now().strftime("%d/%m/%Y %H:%M")
            ws['D4'].font = Font(name='Segoe UI', size=11, bold=True, color="404040")
            ws['D4'].alignment = align_center
            ws['D4'].border = Border(bottom=Side(style='thick', color="1F4E78"))

            # HEADERS AGRUPADOS
            col_idx = 1
            for grp_id, info in self.GRUPOS_INFO.items():
                cols_grupo = [c for c in self.COLUMNAS_DEF if c[3] == grp_id]
                if not cols_grupo: continue
                
                start_col = col_idx
                end_col = col_idx + len(cols_grupo) - 1
                ws.merge_cells(start_row=5, start_column=start_col, end_row=5, end_column=end_col)
                cell = ws.cell(row=5, column=start_col)
                cell.value = info['titulo']
                cell.font = font_grupo
                cell.fill = PatternFill(start_color=info['color'], end_color=info['color'], fill_type="solid")
                cell.alignment = align_center
                cell.border = Border(right=border_med, left=border_med)
                col_idx += len(cols_grupo)

            # HEADERS COLUMNAS
            col_idx = 1
            for def_col in self.COLUMNAS_DEF:
                grp_id = def_col[3]
                color_base = self.GRUPOS_INFO[grp_id]['color']
                cell = ws.cell(row=6, column=col_idx)
                cell.value = def_col[1]
                cell.fill = PatternFill(start_color=color_base, end_color=color_base, fill_type="solid")
                cell.font = font_header
                cell.alignment = align_center
                cell.border = borde_cuadro
                ws.column_dimensions[get_column_letter(col_idx)].width = def_col[2]
                col_idx += 1
            
            ws.row_dimensions[5].height = 25
            ws.row_dimensions[6].height = 35

            # DATOS
            cols_moneda = [i+1 for i, c in enumerate(self.COLUMNAS_DEF) if c[3] == 4]
            col_pdf = [i+1 for i, c in enumerate(self.COLUMNAS_DEF) if c[0] == 'Ruta_PDF'][0]
            col_factura = [i+1 for i, c in enumerate(self.COLUMNAS_DEF) if c[0] == 'Numero_Factura'][0]

            for row in ws.iter_rows(min_row=self.fila_inicio_datos):
                fill = PatternFill(start_color="F9F9F9", end_color="F9F9F9", fill_type="solid") if row[0].row % 2 == 0 else None
                for cell in row:
                    if fill: cell.fill = fill
                    cell.font = font_data
                    cell.border = borde_cuadro
                    cell.alignment = Alignment(vertical='center')
                    
                    if cell.col_idx in cols_moneda:
                        cell.number_format = '_-$ * #,##0.00_-;-$ * #,##0.00_-;_-;_-@'
                        cell.alignment = Alignment(horizontal='right', vertical='center')
                    
                    if cell.col_idx == col_factura:
                        cell.font = Font(name='Segoe UI', size=9, bold=True)
                        cell.alignment = align_center
                    
                    if cell.col_idx == col_pdf:
                        path = cell.value
                        if path and isinstance(path, str) and os.path.exists(path):
                            cell.value = "Abrir PDF"
                            cell.hyperlink = path
                            cell.font = Font(name='Segoe UI', size=9, color="0000FF", underline="single", bold=True)
                            cell.alignment = align_center
                        elif not path:
                            cell.value = "-"
                            cell.alignment = align_center

            ws.freeze_panes = 'D7' 
            ws.auto_filter.ref = f"A6:{get_column_letter(len(self.COLUMNAS_DEF))}{ws.max_row}"
            wb.save(self.nombre_archivo)
            
        except Exception as e:
            log(98, f"Error formato visual Pro: {e}", "ERROR")

def generar_excel_final(nombre_archivo, datos_completos):
    generador = GeneradorExcel(nombre_archivo)
    return generador.generar(datos_completos)