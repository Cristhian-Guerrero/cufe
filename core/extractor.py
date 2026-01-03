"""
═══════════════════════════════════════════════════════════════════════════
EXTRACTOR DE DATOS PDF - CUFE DIAN AUTOMATION (FINAL PRECISION)
v6.7 - Corrección Tipo de Operación y limpieza total de campos pegados
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
        """Limpia basura técnica al final de los nombres"""
        if not texto: return ""
        texto = re.sub(r'\s+\d+\s*\d*$', '', texto)
        return texto.strip(" .,;-")

    @staticmethod
    def limpiar_monto(texto):
        """Convierte texto financiero a float"""
        if not texto: return 0
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

    def _limpiar_valor_fiscal(self, texto):
        """
        TIJERA INTELIGENTE: Corta el texto cuando encuentra datos que no pertenecen
        al campo actual.
        """
        if not texto: return ""
        
        texto = self.limpiar_texto(texto)
        
        # Palabras que indican el inicio del SIGUIENTE campo (basura para el actual)
        palabras_corte = [
            'País', 'Pais', 'Departamento', 'Municipio', 'Ciudad', 
            'Dirección', 'Direccion', 'Teléfono', 'Telefono', 'Móvil', 
            'Correo', 'Email', 'Forma de pago', 'Medio de Pago',
            'Régimen', 'Responsabilidad', 'Actividad'
        ]
        
        for palabra in palabras_corte:
            if palabra in texto:
                texto = texto.split(palabra)[0]
            # Caso especial para pegados sin espacio "01-IVAPaís"
            if len(texto) > 15 and palabra in texto: 
                 texto = texto.split(palabra)[0]

        return texto.strip(" .,;-|:")

    def _procesar_nombre_adquiriente(self, nombre_bruto, datos):
        if not nombre_bruto: 
            datos['Adq_RazonSocial'] = ''
            datos['Adq_NombreComercial'] = ''
            return

        limpio = self.limpiar_nombre_puro(nombre_bruto)
        
        if '/' in limpio:
            partes = limpio.split('/')
            if len(partes) >= 2:
                comercial = partes[0].strip()
                legal = partes[1].strip()
                if len(legal) > 2:
                    datos['Adq_NombreComercial'] = comercial
                    datos['Adq_RazonSocial'] = legal 
                else:
                    datos['Adq_RazonSocial'] = limpio
            else:
                datos['Adq_RazonSocial'] = limpio
        else:
            datos['Adq_RazonSocial'] = limpio
            datos['Adq_NombreComercial'] = ''

    def extraer_datos(self, ruta_pdf, cufe_original, numero):
        ruta_pdf_absoluta = os.path.abspath(ruta_pdf)
        
        datos = {
            'Numero': numero, 'Estado': '✅ Procesado', 'Ruta_PDF': ruta_pdf_absoluta, 'Notas': '',
            'CUFE': cufe_original, 'Numero_Factura': '', 'Fecha_Emision': '', 'Fecha_Vencimiento': '',
            'Tipo_Operacion': '', 'Forma_Pago': '', 'Medio_Pago': '', 'Orden_Pedido': '', 'Moneda': 'COP',
            'Eventos': '', 
            
            # EMISOR
            'Emisor_RazonSocial': '', 'Emisor_NombreComercial': '', 'Emisor_NIT': '',
            'Emisor_TipoContribuyente': '', 'Emisor_RegimenFiscal': '', 'Emisor_Responsabilidad': '',
            'Emisor_ActividadEconomica': '', 'Emisor_Pais': '',
            'Emisor_Departamento': '', 'Emisor_Municipio': '',
            'Emisor_Direccion': '', 'Emisor_Telefono': '', 'Emisor_Correo': '',
            
            # ADQUIRIENTE
            'Adq_RazonSocial': '', 'Adq_NombreComercial': '', 'Adq_Tipo': '',
            'Adq_NumeroDocumento': '', 'Adq_TipoDocumento': '', 
            'Adq_Pais': '', 'Adq_Responsabilidad': '', 'Adq_RegimenFiscal': '',
            'Adq_Departamento': '', 'Adq_Municipio': '', 
            'Adq_Direccion': '', 'Adq_Telefono': '', 'Adq_Correo': '',
            
            # FINANCIERO
            'Subtotal': 0, 'Total_Bruto': 0, 
            'IVA': 0, 'INC': 0, 'Bolsas': 0, 'Otros_Impuestos': 0,
            'Total_Factura': 0, 'Anticipos': 0, 
            'Rete_Fuente': 0, 'Rete_IVA': 0, 'Rete_ICA': 0
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
        
        # --- CORRECCIÓN TIPO OPERACIÓN ---
        # Corta si encuentra "Fecha", "Orden" o "Forma" pegado al final
        m = re.search(r'Tipo de Operación:\s*([^\n]+)', texto); 
        if m: 
            val = self.limpiar_texto(m.group(1))
            palabras_corte = ['Fecha', 'Orden', 'Forma', 'Medio']
            for p in palabras_corte:
                if p in val:
                    val = val.split(p)[0]
            datos['Tipo_Operacion'] = val.strip()

        m = re.search(r'Forma de pago:\s*([^\n]+)', texto); 
        if m: datos['Forma_Pago'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Medio de Pago:\s*([^\n]+)', texto); 
        if m: datos['Medio_Pago'] = self._limpiar_valor_fiscal(m.group(1))

    def _extraer_emisor(self, datos, texto):
        bloque = re.search(r'Datos del Emisor(.*?)Datos del Adquiriente', texto, re.DOTALL | re.IGNORECASE)
        txt = bloque.group(1) if bloque else texto
        
        m = re.search(r'Razón Social:\s*([^\n]+)', txt); 
        if m: datos['Emisor_RazonSocial'] = self.limpiar_nombre_puro(m.group(1))
        m = re.search(r'Nit del Emisor:\s*([\d\.-]+)', txt); 
        if m: datos['Emisor_NIT'] = m.group(1)
        m = re.search(r'Tipo de Contribuyente:\s*([^\n]+)', txt); 
        if m: datos['Emisor_TipoContribuyente'] = self._limpiar_valor_fiscal(m.group(1))
        
        # Corrección Fiscales Emisor (Tijera inteligente)
        m = re.search(r'Régimen Fiscal:(.+)', txt); 
        if m: 
            val = re.split(r'Responsabilidad|Actividad', m.group(1))[0]
            datos['Emisor_RegimenFiscal'] = self._limpiar_valor_fiscal(val)

        m = re.search(r'Responsabilidad tributaria:\s*(.+)', txt); 
        if m: 
            val = re.split(r'Actividad|País|Pais', m.group(1))[0]
            datos['Emisor_Responsabilidad'] = self._limpiar_valor_fiscal(val)

        m = re.search(r'Actividad Económica:\s*([^\n]*)', txt);
        if m: 
            val = m.group(1).strip()
            # Si captura basura (teléfono, pago), es porque estaba vacío
            if any(x in val for x in ["Teléfono", "Forma de pago", "Medio"]) or len(val) < 2:
                datos['Emisor_ActividadEconomica'] = ""
            else:
                datos['Emisor_ActividadEconomica'] = self._limpiar_valor_fiscal(val)
        
        # Ubicación Emisor
        m = re.search(r'País:\s*([^\n]+)', txt);
        if m: datos['Emisor_Pais'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Dirección:\s*([^\n]+)', txt); 
        if m: datos['Emisor_Direccion'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Municipio / Ciudad:\s*([^\n]+)', txt); 
        if m: datos['Emisor_Municipio'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Departamento:\s*([^\n]+)', txt); 
        if m: datos['Emisor_Departamento'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Correo:\s*([^\n]+)', txt);
        if m: datos['Emisor_Correo'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Teléfono / Móvil:\s*([^\n]+)', txt);
        if m: datos['Emisor_Telefono'] = self._limpiar_valor_fiscal(m.group(1))

    def _extraer_adquiriente(self, datos, texto):
        bloque = re.search(r'Datos del Adquiriente(.*?)Detalles de Productos', texto, re.DOTALL | re.IGNORECASE)
        txt = bloque.group(1) if bloque else texto
        
        m = re.search(r'Tipo de Contribuyente:\s*([^\n]+)', txt)
        if m: 
            val = self._limpiar_valor_fiscal(m.group(1))
            if 'Jurídica' in val or 'Juridica' in val: datos['Adq_Tipo'] = 'Jurídica'
            elif 'Natural' in val: datos['Adq_Tipo'] = 'Natural'
            else: datos['Adq_Tipo'] = val

        m = re.search(r'(?:Nombre o )?Razón Social:\s*([^\n]+)', txt)
        if m: self._procesar_nombre_adquiriente(m.group(1), datos)

        m = re.search(r'Número Documento:\s*([\d\.-]+)', txt); 
        if m: datos['Adq_NumeroDocumento'] = m.group(1)
        
        # Corrección Fiscales Cliente
        m = re.search(r'Responsabilidad tributaria:\s*([^\n]+)', txt);
        if m: datos['Adq_Responsabilidad'] = self._limpiar_valor_fiscal(m.group(1))
        
        m = re.search(r'Régimen fiscal:\s*([^\n]+)', txt);
        if m: datos['Adq_RegimenFiscal'] = self._limpiar_valor_fiscal(m.group(1))
        
        m = re.search(r'País:\s*([^\n]+)', txt);
        if m: datos['Adq_Pais'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Dirección:\s*([^\n]+)', txt); 
        if m: datos['Adq_Direccion'] = self.limpiar_texto(m.group(1)) 
        m = re.search(r'Municipio / Ciudad:\s*([^\n]+)', txt); 
        if m: datos['Adq_Municipio'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Departamento:\s*([^\n]+)', txt); 
        if m: datos['Adq_Departamento'] = self._limpiar_valor_fiscal(m.group(1))
        m = re.search(r'Correo:\s*([^\n]+)', txt); 
        if m: datos['Adq_Correo'] = self.limpiar_texto(m.group(1))
        m = re.search(r'Teléfono / Móvil:\s*([^\n]+)', txt);
        if m: datos['Adq_Telefono'] = self._limpiar_valor_fiscal(m.group(1))

    def _extraer_totales(self, datos, texto):
        patrones = {
            'Subtotal': [r'Subtotal\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', r'"Subtotal\s*",,"([\d\.,]+)'],
            'Total_Bruto': [r'Total Bruto Factura\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'],
            'IVA': [r'IVA\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', r'Total impuesto.*?(=).*?([\d\.,]+)'],
            'INC': [r'INC\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'],
            'Bolsas': [r'Bolsas\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'],
            'Otros_Impuestos': [r'Otros impuestos\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'],
            'Total_Factura': [r'Total factura\s*\(=\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', r'Total a Pagar.*?([\d\.,]+)'],
            'Anticipos': [r'Anticipos\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', r'ANTICIPOS\s*[\n\r]*\s*([\d\.,]+)'],
            'Rete_Fuente': [r'Rete fuente\s*"?([\d\.,]+)"?', r'Retención en la fuente.*?([\d\.,]+)'],
            'Rete_ICA': [r'Rete ICA\s*"?([\d\.,]+)"?'],
            'Rete_IVA': [r'Rete IVA\s*"?([\d\.,]+)"?']
        }
        for campo, lista_regex in patrones.items():
            for regex in lista_regex:
                m = re.search(regex, texto, re.IGNORECASE | re.DOTALL)
                if m:
                    valor = m.group(m.lastindex)
                    datos[campo] = self.limpiar_monto(valor)
                    break

def extraer_datos_pdf(ruta_pdf, cufe_original, numero):
    extractor = ExtractorPDF()
    return extractor.extraer_datos(ruta_pdf, cufe_original, numero)