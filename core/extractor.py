"""
═══════════════════════════════════════════════════════════════════════════
EXTRACTOR DE DATOS PDF - CUFE DIAN AUTOMATION (MULTI-FORMATO)
v7.5 - FIX CRÍTICO: IVA capturaba teléfono del adquiriente
═══════════════════════════════════════════════════════════════════════════

FIX v7.5:
1. _extraer_totales ahora busca SOLO en bloque "Datos Totales" (no en todo el texto)
2. Validación de montos: rechaza valores > 100 mil millones (teléfonos capturados)
3. Regex de IVA no salta líneas para evitar capturar campo siguiente
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
        texto = re.sub(r'[\u3164\ufeff\u200b-\u200f\u202a-\u202e]', '', texto)
        return re.sub(r'\s+', ' ', texto).strip()
    
    @staticmethod
    def limpiar_nombre_puro(texto):
        if not texto: return ""
        texto = re.sub(r'\s+\d+\s*\d*$', '', texto)
        return texto.strip(" .,;-")

    @staticmethod
    def limpiar_monto(texto):
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

    @staticmethod
    def _validar_monto(valor):
        """
        FIX v7.5: Valida que un monto sea razonable.
        Rechaza valores absurdamente grandes que son teléfonos capturados por error.
        Límite: 100 mil millones COP (ninguna factura individual supera esto)
        """
        if valor is None:
            return 0
        if isinstance(valor, (int, float)):
            if abs(valor) > 100_000_000_000:  # 100 mil millones
                return 0
            return valor
        return 0

    def _limpiar_campo_pegado(self, texto, palabras_corte):
        if not texto: return ""
        
        texto = self.limpiar_texto(texto)
        
        etiquetas_campos = [
            'Actividad Económica', 'Actividad', 'Teléfono', 'Tel:', 'Móvil',
            'Correo', 'Email', 'Dirección', 'Municipio', 'Ciudad', 
            'Departamento', 'País', 'Pais', 'Régimen', 'Responsabilidad', 
            'NIT', 'Nit', 'Número', 'Tipo de'
        ]
        
        for etiqueta in etiquetas_campos:
            if texto.startswith(etiqueta + ':') or texto.startswith(etiqueta + ' '):
                return ""
        
        pos_corte = len(texto)
        for palabra in palabras_corte:
            match = re.search(rf'\b{re.escape(palabra)}\b', texto, re.IGNORECASE)
            if match and match.start() < pos_corte:
                pos_corte = match.start()
        
        resultado = texto[:pos_corte].strip(" .,;-|:")
        
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
        ruta_pdf_absoluta = os.path.abspath(ruta_pdf)
        
        datos = {
            'Numero': numero, 'Estado': '✅ Procesado', 'Ruta_PDF': ruta_pdf_absoluta, 'Notas': '',
            'CUFE': cufe_original, 'Numero_Factura': '', 'Fecha_Emision': '', 'Fecha_Vencimiento': '',
            'Tipo_Operacion': '', 'Forma_Pago': '', 'Medio_Pago': '', 'Orden_Pedido': '', 'Moneda': 'COP',
            'Eventos': '', 
            'Emisor_RazonSocial': '', 'Emisor_NombreComercial': '', 'Emisor_NIT': '',
            'Emisor_TipoContribuyente': '', 'Emisor_RegimenFiscal': '', 'Emisor_Responsabilidad': '',
            'Emisor_ActividadEconomica': '', 'Emisor_Pais': '',
            'Emisor_Departamento': '', 'Emisor_Municipio': '',
            'Emisor_Direccion': '', 'Emisor_Telefono': '', 'Emisor_Correo': '',
            'Adq_RazonSocial': '', 'Adq_NombreComercial': '', 'Adq_Tipo': '',
            'Adq_NumeroDocumento': '', 'Adq_TipoDocumento': '', 
            'Adq_Pais': '', 'Adq_Responsabilidad': '', 'Adq_RegimenFiscal': '',
            'Adq_Departamento': '', 'Adq_Municipio': '', 
            'Adq_Direccion': '', 'Adq_Telefono': '', 'Adq_Correo': '',
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
        m = re.search(r'CU[FD][ES]:?\s*([\w\n]+)', texto, re.IGNORECASE)
        if m: datos['CUFE'] = m.group(1).replace('\n', '').strip()[:100]
        
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
                if '-' in fecha:
                    partes = fecha.split('-')
                    if len(partes) == 3:
                        fecha = f"{partes[2]}/{partes[1]}/{partes[0]}"
                datos['Fecha_Emision'] = fecha
                break
        
        patrones_vencimiento = [
            r'Fecha de Vencimiento:\s*(\d{2}/\d{2}/\d{4})',
            r'Fecha de vencimiento:\s*(\d{2}/\d{2}/\d{4})',
        ]
        for patron in patrones_vencimiento:
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                datos['Fecha_Vencimiento'] = m.group(1)
                break
        
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
        bloque = re.search(
            r'Datos del [Ee]misor(.*?)Datos del (?:Adquiriente|[Aa]dquirente|[Rr]eceptor|[Cc]omprador)',
            texto, re.DOTALL | re.IGNORECASE
        )
        txt = bloque.group(1) if bloque else texto
        
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
        
        m = re.search(r'Nombre [Cc]omercial:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Nit', 'NIT', 'País', 'Tipo'])
            if val:
                datos['Emisor_NombreComercial'] = self.limpiar_nombre_puro(val)
        
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
        
        m = re.search(r'Tipo de [Cc]ontribuyente:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Régimen', 'Departamento', 'Municipio'])
            if val:
                datos['Emisor_TipoContribuyente'] = val
        
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

        m = re.search(r'Actividad Económica:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Correo', 'Email'])
            if val and not val.startswith('Teléfono'):
                datos['Emisor_ActividadEconomica'] = val
        
        m = re.search(r'País:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Departamento', 'Depto'])
            if val:
                datos['Emisor_Pais'] = val
        
        m = re.search(r'Departamento:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Municipio', 'Ciudad'])
            if val:
                datos['Emisor_Departamento'] = val
        
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
        
        m = re.search(r'Dirección:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Móvil', 'Correo', 'Email'])
            if val and val != 'No aplica':
                datos['Emisor_Direccion'] = val
        
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
        
        m = re.search(r'Correo:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self.limpiar_texto(m.group(1))
            if '@' in val and '.' in val:
                email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', val)
                if email_match:
                    datos['Emisor_Correo'] = email_match.group(1)

    def _extraer_adquiriente(self, datos, texto):
        bloque = re.search(
            r'Datos del (?:Adquiriente|[Aa]dquirente|[Rr]eceptor|[Cc]omprador)(.*?)(?:Detalles de Productos|Detalle[s]? de [Pp]roducto|TOTALES|Referencias)',
            texto, re.DOTALL | re.IGNORECASE
        )
        txt = bloque.group(1) if bloque else texto
        
        m = re.search(r'Tipo de [Cc]ontribuyente:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Régimen', 'Responsabilidad'])
            if 'Jurídica' in val or 'Juridica' in val: datos['Adq_Tipo'] = 'Jurídica'
            elif 'Natural' in val: datos['Adq_Tipo'] = 'Natural'
            elif val: datos['Adq_Tipo'] = val

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
        
        m = re.search(r'Responsabilidad tributaria:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Dirección', 'Correo'])
            if val:
                datos['Adq_Responsabilidad'] = val
        
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
        
        m = re.search(r'País:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Departamento', 'Depto'])
            if val:
                datos['Adq_Pais'] = val
        
        m = re.search(r'Departamento:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Municipio', 'Ciudad'])
            if val:
                datos['Adq_Departamento'] = val
        
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
        
        m = re.search(r'Dirección:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self._limpiar_campo_pegado(m.group(1), ['Teléfono', 'Tel:', 'Móvil', 'Correo'])
            if val and val != 'No aplica':
                datos['Adq_Direccion'] = val
        
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
        
        m = re.search(r'Correo:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self.limpiar_texto(m.group(1))
            if '@' in val and '.' in val:
                email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', val)
                if email_match:
                    datos['Adq_Correo'] = email_match.group(1)

    def _extraer_totales(self, datos, texto):
        """
        ═══════════════════════════════════════════════════════════════
        FIX v7.5 CRÍTICO: Extraer totales SOLO del bloque financiero
        
        PROBLEMA: El regex de IVA encontraba "01 - IVA" en la sección
        del adquiriente (Responsabilidad tributaria: 01 - IVA) y 
        capturaba el teléfono como valor del IVA.
        
        SOLUCIÓN: 
        1. Delimitar búsqueda al bloque "Datos Totales" / "TOTALES"
        2. Si no encuentra bloque, usar fallback desde "Subtotal"
        3. Validar que montos no excedan 100 mil millones COP
        ═══════════════════════════════════════════════════════════════
        """
        
        # ========== FIX v7.5: DELIMITAR BLOQUE DE TOTALES ==========
        bloque_totales = None
        
        # Intento 1: Buscar sección "Datos Totales"
        m_bloque = re.search(
            r'(?:Datos\s+Totales|DATOS\s+TOTALES)(.*?)(?:Numero de Autorización|Hoja \d|$)',
            texto, re.DOTALL | re.IGNORECASE
        )
        if m_bloque:
            bloque_totales = m_bloque.group(1)
        
        # Intento 2: Buscar desde "Subtotal" hasta el final
        if not bloque_totales:
            m_bloque = re.search(
                r'(Subtotal.*?)(?:Numero de Autorización|Hoja \d|$)',
                texto, re.DOTALL | re.IGNORECASE
            )
            if m_bloque:
                bloque_totales = m_bloque.group(1)
        
        # Intento 3: Fallback - usar todo el texto (comportamiento anterior)
        if not bloque_totales:
            bloque_totales = texto
            log(99, "⚠️ No se encontró bloque de totales, usando texto completo", "WARN")
        # ========== FIN FIX v7.5 ==========
        
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
                # FIX v7.5: Buscar "IVA" como campo independiente (NO dentro de "01 - IVA")
                # Requiere que "IVA" esté al inicio de línea o después de espacio/tabulador
                r'(?:^|\n)\s*IVA\s+([\d\.,]+)',
                r'(?:^|\n)\s*IVA\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total IVA\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Total impuesto\s*\(=\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ],
            'INC': [
                r'(?:^|\n)\s*INC\s+([\d\.,]+)',
                r'(?:^|\n)\s*INC\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
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
        
        # FIX v7.5: Buscar en bloque delimitado, NO en texto completo
        for campo, lista_regex in patrones.items():
            for regex in lista_regex:
                m = re.search(regex, bloque_totales, re.IGNORECASE | re.DOTALL | re.MULTILINE)
                if m:
                    valor = m.group(m.lastindex)
                    monto = self.limpiar_monto(valor)
                    # FIX v7.5: Validar que el monto sea razonable
                    datos[campo] = self._validar_monto(monto)
                    break

def extraer_datos_pdf(ruta_pdf, cufe_original, numero, tipo_documento=None):
    extractor = ExtractorPDF()
    return extractor.extraer_datos(ruta_pdf, cufe_original, numero, tipo_documento)