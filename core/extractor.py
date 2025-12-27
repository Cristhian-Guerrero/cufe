"""
═══════════════════════════════════════════════════════════════════════════
EXTRACTOR DE DATOS PDF - CUFE DIAN AUTOMATION (SIMPLE & CLEAN)
v6.0 - Enfoque Contable: Solo Razón Social y Nombre Comercial
═══════════════════════════════════════════════════════════════════════════
"""

import os
import re
import pdfplumber
from utils import log

class ExtractorPDF:
    def __init__(self):
        pass

    @staticmethod
    def limpiar_texto(texto):
        if not texto: return ""
        return re.sub(r'\s+', ' ', texto).strip()
    
    @staticmethod
    def limpiar_nombre_puro(texto):
        """
        Limpia basura técnica al final (ej: ' 01 00')
        """
        if not texto: return ""
        # Quitar números de control al final que pone el software
        texto = re.sub(r'\s+\d+\s*\d*$', '', texto)
        return texto.strip(" .,;-")

    @staticmethod
    def limpiar_monto(texto):
        if not texto: return "0"
        limpio = re.sub(r'[^\d,.-]', '', texto)
        try:
            if ',' in limpio and '.' in limpio:
                if limpio.rfind(',') > limpio.rfind('.'): 
                    limpio = limpio.replace('.', '').replace(',', '.')
                else: 
                    limpio = limpio.replace(',', '')
            elif ',' in limpio: 
                 limpio = limpio.replace(',', '.')
            elif '.' in limpio:
                 if limpio.count('.') > 1: limpio = limpio.replace('.', '')
            return float(limpio)
        except:
            return 0

    def _procesar_nombre_adquiriente(self, nombre_bruto, datos):
        """
        Separa lógicamente en Razón Social (Legal) y Nombre Comercial (Establecimiento)
        usando el separador '/' si existe.
        """
        if not nombre_bruto: 
            datos['Adq_RazonSocial'] = ''
            datos['Adq_NombreComercial'] = ''
            return

        limpio = self.limpiar_nombre_puro(nombre_bruto)
        
        if '/' in limpio:
            partes = limpio.split('/')
            # LOGICA: ESTABLECIMIENTO / PROPIETARIO
            # Parte Izquierda: Nombre Comercial (Ej: DROGUERIA LA 50)
            # Parte Derecha: Razón Social Legal (Ej: MARIA PEREZ)
            if len(partes) >= 2:
                comercial = partes[0].strip()
                legal = partes[1].strip()
                
                # A veces el software pone basura en un lado, validamos
                if len(legal) > 2:
                    datos['Adq_NombreComercial'] = comercial
                    datos['Adq_RazonSocial'] = legal # Este es el que importa fiscalmente
                else:
                    datos['Adq_RazonSocial'] = limpio
            else:
                datos['Adq_RazonSocial'] = limpio
        else:
            # Si no hay slash, todo es Razón Social
            datos['Adq_RazonSocial'] = limpio
            datos['Adq_NombreComercial'] = '' # No aplica

    def extraer_datos(self, ruta_pdf, cufe_original, numero):
        ruta_pdf_absoluta = os.path.abspath(ruta_pdf)
        
        datos = {
            'Numero': numero, 'Estado': '✅ Procesado', 'Ruta_PDF': ruta_pdf_absoluta, 'Notas': '',
            'CUFE': cufe_original, 'Numero_Factura': '', 'Fecha_Emision': '', 'Fecha_Vencimiento': '',
            'Tipo_Operacion': '', 'Forma_Pago': '', 'Medio_Pago': '', 'Orden_Pedido': '', 'Moneda': 'COP',
            
            # EMISOR
            'Emisor_RazonSocial': '', 'Emisor_NombreComercial': '', 'Emisor_NIT': '',
            'Emisor_TipoContribuyente': '', 'Emisor_RegimenFiscal': '', 'Emisor_Responsabilidad': '',
            'Emisor_ActividadEconomica': '', 'Emisor_Departamento': '', 'Emisor_Municipio': '',
            'Emisor_Direccion': '', 'Emisor_Telefono': '', 'Emisor_Correo': '',
            
            # ADQUIRIENTE (SIMPLIFICADO)
            'Adq_RazonSocial': '',       # El nombre legal (Persona o Empresa)
            'Adq_NombreComercial': '',   # El nombre del establecimiento (si hay /)
            'Adq_Tipo': '',              # Natural / Juridica
            'Adq_NumeroDocumento': '', 'Adq_TipoDocumento': '', 
            'Adq_Departamento': '', 'Adq_Municipio': '', 
            'Adq_Direccion': '', 'Adq_Telefono': '', 'Adq_Correo': '',
            
            # TOTALES
            'Total_Moneda': 'COP', 'Subtotal': 0, 'Descuento_Detalle': 0, 'Recargo_Detalle': 0, 
            'Total_Bruto': 0, 'IVA': 0, 'INC': 0, 'Bolsas': 0, 'Otros_Impuestos': 0,
            'Total_Neto': 0, 'Descuento_Global': 0, 'Total_Factura': 0, 
            'Anticipos': 0, 'Rete_Fuente': 0, 'Rete_IVA': 0, 'Rete_ICA': 0
        }
        
        if not os.path.exists(ruta_pdf_absoluta):
            datos['Estado'] = '❌ PDF no encontrado'
            return datos
        
        try:
            with pdfplumber.open(ruta_pdf_absoluta) as pdf:
                texto_completo = ""
                for pagina in pdf.pages:
                    txt = pagina.extract_text()
                    if txt: texto_completo += txt + "\n"
                
                if not texto_completo.strip():
                    datos['Estado'] = '⚠️ PDF sin texto'
                    return datos

                self._extraer_documento(datos, texto_completo)
                self._extraer_emisor(datos, texto_completo)
                self._extraer_adquiriente(datos, texto_completo)
                self._extraer_totales(datos, texto_completo)
                
        except Exception as e:
            log(99, f"Error: {str(e)[:50]}", "ERROR")
            datos['Estado'] = f'❌ Error Lectura'
        
        return datos

    def _extraer_documento(self, datos, texto):
        m = re.search(r'CUFE:?\s*([\w\n]+)', texto); 
        if m: datos['CUFE'] = m.group(1).replace('\n', '').strip()[:100]
        m = re.search(r'Número de Factura:\s*([A-Z0-9\-]+)', texto); 
        if m: datos['Numero_Factura'] = m.group(1)
        m = re.search(r'Fecha de Emisión:\s*(\d{2}/\d{2}/\d{4})', texto); 
        if m: datos['Fecha_Emision'] = m.group(1)
        m = re.search(r'Fecha de Vencimiento:\s*(\d{2}/\d{2}/\d{4})', texto); 
        if m: datos['Fecha_Vencimiento'] = m.group(1)
        m = re.search(r'Tipo de Operación:\s*([^\n]+)', texto); 
        if m: datos['Tipo_Operacion'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Forma de pago:\s*([^\n]+)', texto); 
        if m: datos['Forma_Pago'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Medio de Pago:\s*([^\n]+)', texto); 
        if m: datos['Medio_Pago'] = self.limpiar_texto(m.group(1))

    def _extraer_emisor(self, datos, texto):
        bloque = re.search(r'Datos del Emisor(.*?)Datos del Adquiriente', texto, re.DOTALL | re.IGNORECASE)
        txt = bloque.group(1) if bloque else texto
        
        m = re.search(r'Razón Social:\s*([^\n]+)', txt); 
        if m: datos['Emisor_RazonSocial'] = self.limpiar_nombre_puro(m.group(1))
        m = re.search(r'Nombre Comercial:\s*([^\n]+)', txt); 
        if m: datos['Emisor_NombreComercial'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Nit del Emisor:\s*([\d\.-]+)', txt); 
        if m: datos['Emisor_NIT'] = m.group(1)
        m = re.search(r'Tipo de Contribuyente:\s*([^\n]+)', txt); 
        if m: datos['Emisor_TipoContribuyente'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Régimen Fiscal:(.+)', txt); 
        if m: datos['Emisor_RegimenFiscal'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Responsabilidad tributaria:\s*(.+)', txt); 
        if m: datos['Emisor_Responsabilidad'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Dirección:\s*([^\n]+)', txt); 
        if m: datos['Emisor_Direccion'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Municipio / Ciudad:\s*([^\n]+)', txt); 
        if m: datos['Emisor_Municipio'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Departamento:\s*([^\n]+)', txt); 
        if m: datos['Emisor_Departamento'] = self.limpiar_texto(m.group(1))

    def _extraer_adquiriente(self, datos, texto):
        bloque = re.search(r'Datos del Adquiriente(.*?)Detalles de Productos', texto, re.DOTALL | re.IGNORECASE)
        txt = bloque.group(1) if bloque else texto
        
        # 1. TIPO (Simple, tal cual sale)
        m = re.search(r'Tipo de Contribuyente:\s*([^\n]+)', txt)
        if m: 
            val = self.limpiar_texto(m.group(1))
            if 'Jurídica' in val or 'Juridica' in val: datos['Adq_Tipo'] = 'Jurídica'
            elif 'Natural' in val: datos['Adq_Tipo'] = 'Natural'
            else: datos['Adq_Tipo'] = val

        # 2. NOMBRE (Lógica Simplificada)
        m = re.search(r'(?:Nombre o )?Razón Social:\s*([^\n]+)', txt)
        if m:
            nombre_full = m.group(1)
            self._procesar_nombre_adquiriente(nombre_full, datos)

        # 3. OTROS DATOS
        m = re.search(r'Número Documento:\s*([\d\.-]+)', txt); 
        if m: datos['Adq_NumeroDocumento'] = m.group(1)
        m = re.search(r'Tipo de Documento:\s*(.+)', txt); 
        if m: datos['Adq_TipoDocumento'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Dirección:\s*([^\n]+)', txt); 
        if m: datos['Adq_Direccion'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Municipio / Ciudad:\s*([^\n]+)', txt); 
        if m: datos['Adq_Municipio'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Departamento:\s*([^\n]+)', txt); 
        if m: datos['Adq_Departamento'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Correo:\s*([^\n]+)', txt); 
        if m: datos['Adq_Correo'] = self.limpiar_texto(m.group(1))

    def _extraer_totales(self, datos, texto):
        patrones = {
            'Subtotal': [r'Subtotal\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', r'"Subtotal\s*",,"([\d\.,]+)'],
            'Total_Factura': [r'Total factura\s*\(=\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', r'Total a Pagar.*?([\d\.,]+)'],
            'IVA': [r'Total impuesto.*?(=).*?([\d\.,]+)', r'IVA\s+([\d,\.]+)'],
            'Rete_Fuente': [r'Rete fuente\s*"?([\d\.,]+)"?', r'Retención en la fuente.*?([\d\.,]+)'],
            'Rete_ICA': [r'Rete ICA\s*"?([\d\.,]+)"?'],
            'Rete_IVA': [r'Rete IVA\s*"?([\d\.,]+)"?']
        }
        for campo, lista_regex in patrones.items():
            for regex in lista_regex:
                m = re.search(regex, texto, re.IGNORECASE | re.DOTALL)
                if m:
                    datos[campo] = self.limpiar_monto(m.group(m.lastindex))
                    break

def extraer_datos_pdf(ruta_pdf, cufe_original, numero):
    extractor = ExtractorPDF()
    return extractor.extraer_datos(ruta_pdf, cufe_original, numero)