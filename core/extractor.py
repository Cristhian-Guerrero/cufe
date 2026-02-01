"""
═══════════════════════════════════════════════════════════════════════════
EXTRACTOR DE DATOS PDF - CUFE DIAN AUTOMATION (MULTI-FORMATO)
v7.4 - VERSIÓN FINAL - Limpieza total de basura pegada
═══════════════════════════════════════════════════════════════════════════

MEJORAS v7.4 (AJUSTE FINAL):
1. Limpieza agresiva de campos pegados
2. Validación estricta de valores extraídos
3. Eliminación de basura Unicode y caracteres extraños
4. Normalización de espacios múltiples
5. Detección inteligente de fin de campo
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
        # Eliminar caracteres Unicode extraños
        texto = re.sub(r'[\u3164\ufeff\u200b-\u200f\u202a-\u202e]', '', texto)
        # Normalizar espacios
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

    def _limpiar_campo_pegado(self, texto, palabras_corte):
        """
        LIMPIADOR QUIRÚRGICO: Corta el texto en la primera aparición de palabras clave
        y detecta campos vacíos para no capturar etiquetas.
        
        Args:
            texto: Texto a limpiar
            palabras_corte: Lista de palabras que indican fin del campo actual
        
        Returns:
            str: Texto limpio sin basura pegada
        """
        if not texto: return ""
        
        texto = self.limpiar_texto(texto)
        
        # ========== NUEVO: DETECCIÓN DE CAMPOS VACÍOS ==========
        # Si el texto capturado empieza con una etiqueta de campo, significa que el campo original está VACÍO
        etiquetas_campos = [
            'Actividad Económica', 'Actividad', 'Teléfono', 'Tel:', 'Móvil',
            'Correo', 'Email', 'Dirección', 'Municipio', 'Ciudad', 
            'Departamento', 'País', 'Pais', 'Régimen', 'Responsabilidad', 
            'NIT', 'Nit', 'Número', 'Tipo de'
        ]
        
        for etiqueta in etiquetas_campos:
            # Verificar si el texto empieza con la etiqueta (con o sin ":")
            if texto.startswith(etiqueta + ':') or texto.startswith(etiqueta + ' '):
                return ""  # Campo vacío, no capturar la etiqueta del siguiente campo
        # ========== FIN NUEVO CÓDIGO ==========
        
        # Buscar la primera palabra de corte
        pos_corte = len(texto)
        for palabra in palabras_corte:
            # Buscar con case insensitive
            match = re.search(rf'\b{re.escape(palabra)}\b', texto, re.IGNORECASE)
            if match and match.start() < pos_corte:
                pos_corte = match.start()
        
        # Cortar y limpiar
        resultado = texto[:pos_corte].strip(" .,;-|:")
        
        # Validación final: si es muy corto o solo números/símbolos, devolver vacío
        if len(resultado) < 2:
            return ""
        if resultado.replace('-', '').replace('.', '').isdigit() and len(resultado) < 4:
            return ""
        
        return resultado

    def _procesar_nombre_adquiriente(self, nombre_bruto, datos):
        if not nombre_bruto: 
            datos['Adq_RazonSocial'] = ''
            datos['Adq_NombreComercial'] = ''
            return

        limpio = self.limpiar_nombre_puro(nombre_bruto)
        
        # Eliminar "/" inicial común en PDFs de la DIAN
        if limpio.startswith('/'):
            limpio = limpio[1:].strip()
        
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

    def extraer_datos(self, ruta_pdf, cufe_original, numero, tipo_documento=None):
        """
        Extrae datos del PDF con soporte para múltiples formatos
        
        Args:
            ruta_pdf: Ruta al archivo PDF
            cufe_original: CUFE del documento
            numero: Número de orden en el proceso
            tipo_documento: Dict con tipo detectado desde HTML (opcional)
        
        Returns:
            dict: Diccionario con todos los datos extraídos
        """
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

                # Extraer con patrones múltiples (compatible con todos los formatos)
                self._extraer_documento(datos, texto_completo)
                self._extraer_emisor(datos, texto_completo)
                self._extraer_adquiriente(datos, texto_completo)
                self._extraer_totales(datos, texto_completo)
                
        except Exception as e:
            log(99, f"Error: {str(e)[:50]}", "ERROR")
            datos['Estado'] = f'❌ Error Lectura'
        
        return datos

    def _extraer_documento(self, datos, texto):
        """Extrae datos del documento con PATRONES MÚLTIPLES"""
        
        # === CUFE/CUDS ===
        m = re.search(r'CU[FD][ES]:?\s*([\w\n]+)', texto, re.IGNORECASE)
        if m: datos['CUFE'] = m.group(1).replace('\n', '').strip()[:100]
        
        # === NÚMERO DE DOCUMENTO (Múltiples variantes) ===
        patrones_numero = [
            r'Número de Factura:\s*([A-Z0-9\-]+)',
            r'Número de documento:\s*([A-Z0-9\-]+)',
            r'Número\s+de\s+Factura\s+Electrónica:\s*([A-Z0-9\-]+)',
            r'Folio:\s*([A-Z0-9\-]+)',
            r'Serie:\s*([A-Z]{2,10})',
            r'Número de nota:\s*([A-Z0-9\-]+)',
            r'N[úu]mero:\s*([A-Z0-9\-]+)',
        ]
        for patron in patrones_numero:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                datos['Numero_Factura'] = m.group(1)
                break
        
        # === FECHA DE EMISIÓN (Múltiples formatos) ===
        patrones_fecha_emision = [
            r'Fecha de Emisión:\s*(\d{2}/\d{2}/\d{4})',
            r'Fecha de emisión:\s*(\d{2}/\d{2}/\d{4})',
            r'Fecha y hora de expedición:\s*(\d{4}-\d{2}-\d{2})',
            r'Fecha de expedición:\s*(\d{4}-\d{2}-\d{2})',
            r'Fecha de generación:\s*(\d{2}/\d{2}/\d{4})',
        ]
        for patron in patrones_fecha_emision:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                fecha = m.group(1)
                # Convertir formato ISO si es necesario
                if '-' in fecha:
                    partes = fecha.split('-')
                    if len(partes) == 3:
                        fecha = f"{partes[2]}/{partes[1]}/{partes[0]}"
                datos['Fecha_Emision'] = fecha
                break
        
        # === FECHA DE VENCIMIENTO ===
        patrones_vencimiento = [
            r'Fecha de Vencimiento:\s*(\d{2}/\d{2}/\d{4})',
            r'Fecha de vencimiento:\s*(\d{2}/\d{2}/\d{4})',
        ]
        for patron in patrones_vencimiento:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                datos['Fecha_Vencimiento'] = m.group(1)
                break
        
        # === TIPO DE OPERACIÓN (LIMPIEZA MEJORADA) ===
        patrones_tipo_op = [
            r'Tipo de Operación:\s*([^\n]+)',
            r'Tipo de operación:\s*([^\n]+)',
        ]
        for patron in patrones_tipo_op:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Fecha', 'Orden', 'Forma', 'Medio'])
                if val:
                    datos['Tipo_Operacion'] = val
                break

        # === FORMA DE PAGO ===
        patrones_forma_pago = [
            r'Forma de pago:\s*([^\n]+)',
            r'Forma de Pago:\s*([^\n]+)',
        ]
        for patron in patrones_forma_pago:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Medio', 'Orden'])
                if val:
                    datos['Forma_Pago'] = val
                break

        # === MEDIO DE PAGO ===
        patrones_medio_pago = [
            r'Medio de Pago:\s*([^\n]+)',
            r'Medio de pago:\s*([^\n]+)',
        ]
        for patron in patrones_medio_pago:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Orden', 'Tipo'])
                if val:
                    datos['Medio_Pago'] = val
                break

    def _extraer_emisor(self, datos, texto):
        """Extrae datos del emisor/vendedor con LIMPIEZA TOTAL"""
        
        # Intentar delimitar bloque de emisor
        bloque = re.search(
            r'Datos del [Ee]misor(.*?)Datos del (?:Adquiriente|[Aa]dquirente|[Rr]eceptor|[Cc]omprador)',
            texto, re.DOTALL | re.IGNORECASE
        )
        txt = bloque.group(1) if bloque else texto
        
        # === RAZÓN SOCIAL DEL EMISOR ===
        patrones_razon_social = [
            r'Razón Social:\s*([^\n]+)',
            r'Razón social:\s*([^\n]+)',
            r'Nombre:\s*([^\n]+)',
            r'Razón social y/o Nombre:\s*([^\n]+)',
            r'Razón social y/o Nombre y apellido:\s*([^\n]+)',
            r'Razón [Ss]ocial [Vv]endedor:\s*([^\n]+)',
        ]
        for patron in patrones_razon_social:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Nombre Comercial', 'Nit', 'NIT', 'Tipo', 'País'])
                if val:
                    datos['Emisor_RazonSocial'] = self.limpiar_nombre_puro(val)
                    break
        
        # === NOMBRE COMERCIAL DEL EMISOR ===
        m = re.search(r'Nombre [Cc]omercial:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Nit', 'NIT', 'País', 'Tipo'])
            if val:
                datos['Emisor_NombreComercial'] = self.limpiar_nombre_puro(val)
        
        # === NIT DEL EMISOR ===
        patrones_nit = [
            r'Nit del Emisor:\s*([\d\.-]+)',
            r'NIT del emisor:\s*([\d\.-]+)',
            r'NIT:\s*([\d\.-]+)',
            r'Número de documento:\s*([\d\.-]+)',
            r'N[úu]mero [Dd]ocumento:\s*([\d\.-]+)',
        ]
        for patron in patrones_nit:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                datos['Emisor_NIT'] = m.group(1).strip()
                break
        
        # === TIPO DE CONTRIBUYENTE ===
        m = re.search(r'Tipo de [Cc]ontribuyente:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Régimen', 'Departamento', 'Municipio'])
            if val:
                datos['Emisor_TipoContribuyente'] = val
        
        # === RÉGIMEN FISCAL (LIMPIEZA TOTAL) ===
        patrones_regimen = [
            r'Régimen [Ff]iscal:\s*([A-Z0-9\-]+)',
            r'Régimen [Ff]iscal:\s*([^\n]+)',
        ]
        for patron in patrones_regimen:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Municipio', 'Responsabilidad', 'Dirección'])
                if val:
                    datos['Emisor_RegimenFiscal'] = val
                    break

        # === RESPONSABILIDAD TRIBUTARIA (LIMPIEZA TOTAL) ===
        patrones_resp = [
            r'Responsabilidad tributaria:\s*([^\n]+)',
        ]
        for patron in patrones_resp:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Actividad', 'Dirección', 'País', 'Correo', 'Teléfono'])
                if val:
                    datos['Emisor_Responsabilidad'] = val
                    break

        # === ACTIVIDAD ECONÓMICA ===
        m = re.search(r'Actividad Económica:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Correo', 'Email'])
            if val and not val.startswith('Teléfono'):
                datos['Emisor_ActividadEconomica'] = val
        
        # === PAÍS ===
        m = re.search(r'País:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Departamento', 'Depto'])
            if val:
                datos['Emisor_Pais'] = val
        
        # === DEPARTAMENTO ===
        m = re.search(r'Departamento:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Municipio', 'Ciudad'])
            if val:
                datos['Emisor_Departamento'] = val
        
        # === MUNICIPIO/CIUDAD ===
        patrones_municipio = [
            r'Municipio / Ciudad:\s*([^\n]+)',
            r'Municipio/Ciudad:\s*([^\n]+)',
            r'Ciudad:\s*([^\n]+)',
        ]
        for patron in patrones_municipio:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Dirección', 'Teléfono'])
                if val:
                    datos['Emisor_Municipio'] = val
                    break
        
        # === DIRECCIÓN ===
        m = re.search(r'Dirección:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Móvil', 'Correo', 'Email'])
            if val and val != 'No aplica':
                datos['Emisor_Direccion'] = val
        
        # === TELÉFONO ===
        patrones_telefono = [
            r'Teléfono / Móvil:\s*([^\n]+)',
            r'Teléfono:\s*([^\n]+)',
            r'Móvil:\s*([^\n]+)',
        ]
        for patron in patrones_telefono:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Correo', 'Email', 'Actividad'])
                if val:
                    datos['Emisor_Telefono'] = val
                    break
        
        # === CORREO ===
        m = re.search(r'Correo:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self.limpiar_texto(m.group(1))
            # Validar que sea un email válido
            if '@' in val and '.' in val:
                # Extraer solo el email si viene con basura
                email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', val)
                if email_match:
                    datos['Emisor_Correo'] = email_match.group(1)

    def _extraer_adquiriente(self, datos, texto):
        """Extrae datos del adquiriente/cliente con LIMPIEZA TOTAL"""
        
        # Intentar delimitar bloque
        bloque = re.search(
            r'Datos del (?:Adquiriente|[Aa]dquirente|[Rr]eceptor|[Cc]omprador)(.*?)(?:Detalles de Productos|Detalle[s]? de [Pp]roducto|TOTALES|Referencias)',
            texto, re.DOTALL | re.IGNORECASE
        )
        txt = bloque.group(1) if bloque else texto
        
        # === TIPO DE CONTRIBUYENTE ===
        m = re.search(r'Tipo de [Cc]ontribuyente:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Régimen', 'Responsabilidad'])
            if 'Jurídica' in val or 'Juridica' in val: datos['Adq_Tipo'] = 'Jurídica'
            elif 'Natural' in val: datos['Adq_Tipo'] = 'Natural'
            elif val: datos['Adq_Tipo'] = val

        # === RAZÓN SOCIAL ADQUIRIENTE ===
        patrones_razon = [
            r'(?:Nombre o )?Razón Social:\s*([^\n]+)',
            r'Razón social:\s*([^\n]+)',
            r'Nombre / Razón social:\s*([^\n]+)',
            r'Nombre:\s*([^\n]+)',
        ]
        for patron in patrones_razon:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Tipo de Documento', 'NIT', 'Número'])
                if val:
                    self._procesar_nombre_adquiriente(val, datos)
                    break

        # === NÚMERO DE DOCUMENTO ===
        patrones_num_doc = [
            r'Número Documento:\s*([\d\.-]+)',
            r'Número de documento:\s*([\d\.-]+)',
            r'NIT:\s*([\d\.-]+)',
            r'N[úu]mero:\s*([\d\.-]+)',
        ]
        for patron in patrones_num_doc:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                datos['Adq_NumeroDocumento'] = m.group(1).strip()
                break
        
        # === RESPONSABILIDAD TRIBUTARIA ===
        m = re.search(r'Responsabilidad tributaria:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Dirección', 'Correo'])
            if val:
                datos['Adq_Responsabilidad'] = val
        
        # === RÉGIMEN FISCAL ===
        patrones_regimen = [
            r'Régimen fiscal:\s*([A-Z0-9\-]+)',
            r'Régimen fiscal:\s*([^\n]+)',
        ]
        for patron in patrones_regimen:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Dirección', 'Teléfono', 'Municipio', 'Responsabilidad'])
                if val:
                    datos['Adq_RegimenFiscal'] = val
                    break
        
        # === PAÍS ===
        m = re.search(r'País:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Departamento', 'Depto'])
            if val:
                datos['Adq_Pais'] = val
        
        # === DEPARTAMENTO ===
        m = re.search(r'Departamento:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Municipio', 'Ciudad'])
            if val:
                datos['Adq_Departamento'] = val
        
        # === MUNICIPIO/CIUDAD ===
        patrones_municipio = [
            r'Municipio / Ciudad:\s*([^\n]+)',
            r'Municipio/Ciudad:\s*([^\n]+)',
            r'Ciudad:\s*([^\n]+)',
        ]
        for patron in patrones_municipio:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Dirección', 'Teléfono'])
                if val:
                    datos['Adq_Municipio'] = val
                    break
        
        # === DIRECCIÓN ===
        m = re.search(r'Dirección:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Móvil', 'Correo'])
            if val and val != 'No aplica':
                datos['Adq_Direccion'] = val
        
        # === TELÉFONO ===
        patrones_telefono = [
            r'Teléfono / Móvil:\s*([^\n]+)',
            r'Teléfono:\s*([^\n]+)',
            r'Móvil:\s*([^\n]+)',
        ]
        for patron in patrones_telefono:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                val = self._limpiar_campo_pegado(m.group(1), ['Correo', 'Email'])
                if val:
                    datos['Adq_Telefono'] = val
                    break
        
        # === CORREO ===
        m = re.search(r'Correo:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self.limpiar_texto(m.group(1))
            if '@' in val and '.' in val:
                email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', val)
                if email_match:
                    datos['Adq_Correo'] = email_match.group(1)

    def _extraer_totales(self, datos, texto):
        """Extrae valores financieros con PATRONES MÚLTIPLES MEJORADOS"""
        patrones = {
            'Subtotal': [
                r'Subtotal\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Subtotal base gravable\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'"Subtotal\s*",,"([\d\.,]+)'
            ],
            'Total_Bruto': [
                r'Total Bruto Factura\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total [Bb]ruto\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total bruto documento\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ],
            'IVA': [
                r'IVA\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total impuesto.*?(=).*?([\d\.,]+)',
                r'Total IVA\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ],
            'INC': [
                r'INC\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'
            ],
            'Bolsas': [
                r'Bolsas\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'
            ],
            'Otros_Impuestos': [
                r'Otros impuestos\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)'
            ],
            'Total_Factura': [
                r'Total factura\s*\(=\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total a Pagar\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'TOTAL A PAGAR\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total neto factura\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total documento\s+COP\s+\$\s*\(=\)\s*([\d\.,]+)',
                r'Total neto documento\s*\(=\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'TOTAL\s+DOCUMENTO\s+COP\s+\$\s+\(=\)\s*([\d\.,]+)',
                r'Total factura\s*\(=\)\s*.*?COP\s*\$\s*\$?\s*([\d\.,]+)',
                r'Total factura\s*\(=\)\s*COP\s*\$\s*([\d\.,]+)',
                r'Total documento\s*.*?COP\s*\$\s*([\d\.,]+)',
            ],
            'Anticipos': [
                r'Anticipos\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'ANTICIPOS\s*[\n\r]*\s*([\d\.,]+)'
            ],
            'Rete_Fuente': [
                r'Rete fuente\s*"?([\d\.,]+)"?',
                r'Retención en la fuente.*?([\d\.,]+)',
                r'ReteFuente\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ],
            'Rete_ICA': [
                r'Rete ICA\s*"?([\d\.,]+)"?',
                r'ReteICA\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ],
            'Rete_IVA': [
                r'Rete IVA\s*"?([\d\.,]+)"?',
                r'ReteIVA\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ]
        }
        
        for campo, lista_regex in patrones.items():
            for regex in lista_regex:
                m = re.search(regex, texto, re.IGNORECASE | re.DOTALL)
                if m:
                    valor = m.group(m.lastindex)
                    datos[campo] = self.limpiar_monto(valor)
                    break

def extraer_datos_pdf(ruta_pdf, cufe_original, numero, tipo_documento=None):
    """
    Función wrapper para mantener compatibilidad
    
    Args:
        ruta_pdf: Ruta al PDF
        cufe_original: CUFE del documento
        numero: Número de orden
        tipo_documento: Info de tipo (opcional, puede ser None)
    """
    extractor = ExtractorPDF()
    return extractor.extraer_datos(ruta_pdf, cufe_original, numero, tipo_documento)