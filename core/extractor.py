"""
═══════════════════════════════════════════════════════════════════════════
EXTRACTOR DE DATOS PDF - CUFE DIAN AUTOMATION (MULTI-FORMATO)
v7.10.0 - Fix raíz: "Precio unitario de venta" es total de línea, no unitario
═══════════════════════════════════════════════════════════════════════════

CAMBIOS v7.10.0 (fix raíz sobre v7.9.0, verificado con PDF real FE-11275):
Se confirmó con el PDF real de FE-11275 (NIT 5595769) que pdfplumber lee
las páginas de continuación (2 y 3) LIMPIAS — no había corrupción de
columnas como se sospechaba. El bug estaba en la fórmula:
1. "Precio unitario de venta" pese al nombre YA es el TOTAL neto de la
   línea (base gravable), no un precio por unidad — v7.9.0 la multiplicaba
   por Cantidad, inflando la base en facturas con líneas de cantidad>1
   (ej. 10 unidades → base 10 veces mayor). Ahora se usa literal.
2. "Precio unitario" sí es genuinamente por unidad, pero viene CON IVA
   incluido (bruto) — Precio unitario×Cantidad−Descuento+Recargo da el
   BRUTO de línea, no la base. Ahora se le resta el IVA ya reportado
   (literal del PDF, sin dividir entre la tarifa) para obtener el neto.
Verificado exacto al centavo en FE-11275 real: Total_Base=1.888.890,47
(esperado 1.888.890,48, 1 céntimo de ruido acumulado en 48 líneas),
Base_19%=1.541.428,56 (esperado ~1.541.428), Base_0%=262.700,00 (incluye
todas las líneas 0% de la factura, no solo gasolina/thinner).

CAMBIOS v7.9.0 (fix redondeo en céntimos, sobre v7.8.0):
La v7.8.0 derivaba la base de líneas gravadas como IVA ÷ % — exacta en
teoría, pero el IVA del PDF YA viene redondeado a 2 decimales, así que
dividirlo de vuelta no reproducía el valor literal impreso en "Precio
unitario"/"Precio unitario de venta" (arrastraba 2-5 céntimos de ruido).
Corregido: la base SIEMPRE se toma literal de la columna de precio
(Precio unitario×Cantidad−Descuento+Recargo, o Precio unitario de
venta×Cantidad) — nunca de una división. IVA ÷ % se usa solo como
referencia interna para elegir cuál de las dos columnas es la neta cuando
ambas están presentes y discrepan (plantillas donde "Precio unitario"
incluye IVA), sin usar el valor derivado como base final.

CAMBIOS v7.8.0 (fix bug base incompleta en facturas multipágina):
1. _extraer_iva_tabla() recuerda el layout de columnas de "Detalles de
   Productos" entre páginas. Antes, si la tabla ocupaba varias páginas, las
   páginas de continuación (solo filas de datos, sin repetir el encabezado
   "IVA"/"%") se descartaban COMPLETAS — perdiendo toda su base gravable.
   Ahora se reutiliza el encabezado de la última tabla de detalles vista,
   aplicado a tablas siguientes con igual número de columnas.
2. Base por línea gravada (5%/19%): PRIORIDAD a derivarla del IVA ya
   reportado en la fila (Base = IVA ÷ %) — exacta por construcción, no
   depende de adivinar cuál columna de precio es neta. Se detectó un caso
   real donde "Precio unitario" traía el valor CON IVA incluido y "Precio
   unitario de venta" era el neto (al revés de lo asumido en v7.7.0). El
   cálculo por Precio unitario × Cantidad − Descuento + Recargo queda como
   respaldo solo para líneas al 0% (exento/excluido, sin IVA del cual
   derivar).
3. Log de diagnóstico: cuenta y reporta cuántas filas de "Detalles de
   Productos" se leyeron y en cuántas páginas, para poder verificar contra
   el número real de líneas de la factura.

CAMBIOS v7.7.0:
1. _extraer_iva_tabla() ahora también calcula la base gravable por línea
   (Precio unitario × Cantidad − Descuento detalle + Recargo detalle, o
   directo desde "Precio unitario de venta" × Cantidad si está disponible)
   y la agrupa por tarifa: Base_19 / Base_5 / Base_0. NO recalcula el IVA,
   solo suma el valor ya reportado por línea (igual que antes).
2. Nuevo _calcular_cuadre_iva(): verifica (no recalcula) que Total_Base
   cuadre con Subtotal y que base×tarifa cuadre con el IVA extraído, con
   tolerancia de redondeo. Resultado en datos['Cuadre_IVA'] = 'OK'/'Revisar'.
3. Filas de la tabla sin Cantidad/Precio unitario detectable, o facturas
   con Cuadre_IVA='Revisar', quedan logueadas con la fila cruda de
   pdfplumber para autodiagnóstico sin necesidad de scripts aparte.

CAMBIOS v7.6.0:
1. extraer_datos() acepta password=NIT para abrir PDFs cifrados
   (portal DIAN cifra el PDF con el NIT ingresado en la búsqueda)
2. IVA dividido en IVA_19 (19%) e IVA_5 (5%) — se elimina campo IVA único

FIX v7.5 (IVA):
1. _extraer_totales ahora busca SOLO en bloque "Datos Totales"
2. Validación de montos: rechaza valores > 100 mil millones
3. Regex de IVA no salta líneas para evitar capturar campo siguiente

FIX v7.5.1 (Teléfono):
4. _extraer_telefono_bloque() maneja pdfplumber mezclando columnas
5. Busca teléfono en misma línea Y en líneas siguientes (hasta 4 líneas)
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
        # pdfplumber inserta | entre columnas adyacentes del PDF.
        # || o m\u00e1s = columna vac\u00eda \u2192 se elimina con un espacio.
        # | \u00fanico en medio = dos valores reales pegados \u2192 separador legible.
        texto = re.sub(r'\|{2,}', ' ', texto)
        texto = texto.strip('|').strip()
        texto = re.sub(r'\|', ' / ', texto)
        return re.sub(r'\s+', ' ', texto).strip()
    
    @staticmethod
    def limpiar_nombre_puro(texto):
        if not texto: return ""
        # Quitar sufijos numéricos que pipe-cleaning puede dejar: " / 8056970" al final
        texto = re.sub(r'\s*/\s*[\d\.\-]*\s*$', '', texto)
        texto = re.sub(r'\s+\d+\s*\d*$', '', texto)
        return texto.strip(" .,;-/")

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

    def _extraer_telefono_bloque(self, txt):
        """
        FIX v7.5.1: Extrae teléfono manejando el caso donde pdfplumber
        pone el número en una línea diferente a la etiqueta.
        
        pdfplumber a veces extrae:
            Teléfono / Móvil:
            Responsabilidad tributaria: 01 - IVA
            60131145226300006013142198618000
        
        En vez de:
            Teléfono / Móvil: 60131145226300006013142198618000
        """
        # Intento 1: Teléfono en la MISMA línea (caso normal)
        patrones_misma_linea = [
            r'Teléfono / Móvil:\s*([\d|+\-()]{7,}[^\n]*)',
            r'Teléfono:\s*([\d|+\-()]{7,}[^\n]*)',
            r'Móvil:\s*([\d|+\-()]{7,}[^\n]*)',
        ]
        for patron in patrones_misma_linea:
            m = re.search(patron, txt, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        
        # Intento 2: Teléfono en SIGUIENTE(S) línea(s) (pdfplumber mezcló columnas)
        # Buscar "Teléfono / Móvil:" y luego un número largo en las siguientes 3 líneas
        m_etiqueta = re.search(r'Teléfono / Móvil:', txt, re.IGNORECASE)
        if m_etiqueta:
            resto = txt[m_etiqueta.end():]
            lineas = resto.split('\n')[:4]  # Revisar hasta 4 líneas después
            for linea in lineas:
                linea = linea.strip()
                # Buscar línea que sea mayoritariamente un número de teléfono
                m_num = re.match(r'^([\d|+\-()]{7,})$', linea)
                if m_num:
                    return m_num.group(1)
        
        return ''

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

    def extraer_datos(self, ruta_pdf, cufe_original, numero, tipo_documento=None, password=None):
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
            'IVA_19': 0, 'IVA_5': 0, 'INC': 0, 'Bolsas': 0, 'Otros_Impuestos': 0,
            'Total_Factura': 0, 'Anticipos': 0,
            'Rete_Fuente': 0, 'Rete_IVA': 0, 'Rete_ICA': 0,
            'Base_19': 0, 'Base_5': 0, 'Base_0': 0, 'Total_Base': 0, 'Cuadre_IVA': ''
        }

        if not os.path.exists(ruta_pdf_absoluta):
            datos['Estado'] = '❌ PDF no encontrado'
            return datos

        try:
            kwargs = {'password': password} if password else {}
            with pdfplumber.open(ruta_pdf_absoluta, **kwargs) as pdf:
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
                self._extraer_iva_tabla(datos, pdf.pages)
                self._calcular_cuadre_iva(datos)

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
                # El NIT solo admite dígitos, puntos y guiones — cualquier otra cosa es ruido
                datos['Emisor_NIT'] = re.sub(r'[^\d\.\-]', '', m.group(1)).strip('.-')
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
        
        # FIX v7.5.1: Usar método robusto para teléfono
        tel = self._extraer_telefono_bloque(txt)
        if tel:
            datos['Emisor_Telefono'] = tel
        
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
        
        # FIX v7.5.1: Usar método robusto para teléfono
        tel = self._extraer_telefono_bloque(txt)
        if tel:
            datos['Adq_Telefono'] = tel
        
        m = re.search(r'Correo:\s*([^\n]+)', txt, re.IGNORECASE)
        if m:
            val = self.limpiar_texto(m.group(1))
            if '@' in val and '.' in val:
                email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', val)
                if email_match:
                    datos['Adq_Correo'] = email_match.group(1)

    def _extraer_iva_tabla(self, datos, paginas):
        """
        Lee la tabla "Detalles de Productos" del PDF (ya desbloqueado):
          - suma el IVA por tarifa: columna IVA → IVA_19 o IVA_5 según %.
          - calcula la BASE gravable por línea y la agrupa por la misma
            tarifa → Base_19 / Base_5 / Base_0. NO recalcula el IVA (se usa
            tal cual lo reporta la columna IVA), solo agrupa la base.

        Layout real confirmado (factura DIAN estándar):
          Nro | Código | Descripción | U/M | Cantidad | Precio unitario |
          Descuento detalle | Recargo detalle | [IMPUESTOS→] IVA | % | INC | %
          | Precio unitario de venta

        OJO: hay DOS columnas "%" (una para IVA, otra para INC, agrupadas
        bajo el super-encabezado "IMPUESTOS"). Se toma el "%" que aparece
        DESPUÉS de la columna IVA y ANTES de INC — nunca el de INC.

        Base por línea: PRIORIDAD a "Precio unitario de venta" — confirmado
        con PDF real (FE-11275) que, pese al nombre, esa columna YA es el
        TOTAL neto de la línea (no un precio por unidad): se usa literal,
        SIN multiplicar por Cantidad. Fallback si falta esa columna:
        (Precio unitario × Cantidad − Descuento + Recargo) − IVA reportado
        — Precio unitario sí es por unidad pero viene CON IVA incluido, y
        restarle el IVA (valor literal del PDF, sin dividir entre la
        tarifa) reproduce el mismo neto exacto al centavo. IVA÷% se usa
        solo como referencia para elegir entre candidatos si ambos están
        presentes y discrepan, nunca como base final.
        Si no hay columnas suficientes para ninguna fórmula, la fila queda
        sin base y se loguea cruda para diagnóstico.

        Sobreescribe los valores de _extraer_totales solo si encuentra datos reales
        en la tabla (tienen prioridad sobre los regex del texto).
        """
        iva_19 = iva_5 = 0.0
        base_19 = base_5 = base_0 = 0.0
        encontrado = False
        filas_debug = []
        total_filas_leidas = 0
        paginas_con_filas = 0

        # Se recuerda el layout de columnas de la ÚLTIMA tabla "Detalles de
        # Productos" encontrada. Cuando esa tabla ocupa varias páginas, el
        # encabezado ("IVA"/"%") solo aparece en la página donde inicia — las
        # páginas de continuación solo traen filas de datos. Sin este layout
        # recordado, esas tablas se descartaban completas (bug: base
        # incompleta en facturas largas/multipágina).
        layout = None  # dict con idx_iva, idx_pct, idx_cant, idx_precio_venta, idx_precio, idx_desc, idx_recargo, num_cols

        for pagina in paginas:
            try:
                tablas = pagina.extract_tables()
                if not tablas:
                    continue

                filas_pagina = 0

                for tabla in tablas:
                    if not tabla or len(tabla) < 1:
                        continue

                    # Buscar fila de encabezado que contenga "IVA" y "%"
                    encabezado = None
                    datos_inicio = 0
                    for i, fila in enumerate(tabla):
                        if fila is None:
                            continue
                        # Normaliza saltos de línea a espacio: el PDF envuelve
                        # etiquetas de encabezado en varias líneas (ej. "Precio\n
                        # unitario de\nventa") y una comparación por substring
                        # como 'PRECIO UNITARIO' in c nunca hace match si el
                        # salto de línea cae justo ahí — bug confirmado con PDF
                        # real, pasó inadvertido en TODAS las versiones previas.
                        celdas = [re.sub(r'\s+', ' ', str(c or '')).strip().upper() for c in fila]
                        if any('IVA' in c for c in celdas) and any(c in ('%', 'TARIFA', '% IVA') for c in celdas):
                            encabezado = celdas
                            datos_inicio = i + 1
                            # El PDF de DIAN usa encabezado en DOS filas: la
                            # fila con "IVA"/"%"/"INC" (detectada arriba) y,
                            # justo encima, una fila fusionada con el
                            # super-título "IMPUESTOS" y, en la MISMA columna
                            # que queda en blanco en la fila de abajo,
                            # "Precio unitario de venta". Sin fusionar ambas
                            # filas, idx_precio_venta nunca se encuentra
                            # (columna en blanco en la fila con IVA/%).
                            if i > 0 and tabla[i - 1]:
                                fila_superior = [re.sub(r'\s+', ' ', str(c or '')).strip().upper() for c in tabla[i - 1]]
                                for col in range(min(len(encabezado), len(fila_superior))):
                                    if not encabezado[col] and fila_superior[col]:
                                        encabezado[col] = fila_superior[col]
                            break

                    if encabezado is not None:
                        # Índice de la columna IVA (valor)
                        idx_iva = next((i for i, c in enumerate(encabezado) if 'IVA' in c and '%' not in c), None)
                        idx_inc = next((i for i, c in enumerate(encabezado) if c == 'INC'), None)

                        # % de IVA: primer "%" DESPUÉS de IVA y ANTES de INC (nunca el de INC)
                        idx_pct = None
                        if idx_iva is not None:
                            limite = idx_inc if (idx_inc is not None and idx_inc > idx_iva) else len(encabezado)
                            idx_pct = next(
                                (i for i in range(idx_iva + 1, limite) if encabezado[i].strip() == '%'),
                                None
                            )
                        if idx_pct is None:
                            idx_pct = next((i for i, c in enumerate(encabezado) if c.strip() == '%'), None)

                        if idx_iva is None or idx_pct is None:
                            continue

                        layout = {
                            'idx_iva': idx_iva,
                            'idx_pct': idx_pct,
                            'idx_cant': next((i for i, c in enumerate(encabezado) if 'CANT' in c), None),
                            'idx_precio_venta': next((i for i, c in enumerate(encabezado) if 'PRECIO UNITARIO' in c and 'VENTA' in c), None),
                            'idx_precio': next((i for i, c in enumerate(encabezado) if 'PRECIO UNITARIO' in c and 'VENTA' not in c), None),
                            'idx_desc': next((i for i, c in enumerate(encabezado) if 'DESCUENTO' in c), None),
                            'idx_recargo': next((i for i, c in enumerate(encabezado) if 'RECARGO' in c), None),
                            'num_cols': len(encabezado),
                        }
                        filas_datos = tabla[datos_inicio:]
                    elif layout is not None and len(tabla[0] or []) == layout['num_cols']:
                        # Tabla de continuación (misma cantidad de columnas que
                        # la tabla de detalles, sin fila de encabezado propia):
                        # se asume que es la misma tabla partida por salto de
                        # página y se procesa completa como filas de datos.
                        filas_datos = tabla
                    else:
                        # No es continuación de "Detalles de Productos"
                        # (p.ej. tablas de Subtotal/Anticipos/Retenciones).
                        continue

                    idx_iva = layout['idx_iva']
                    idx_pct = layout['idx_pct']
                    idx_cant = layout['idx_cant']
                    idx_precio_venta = layout['idx_precio_venta']
                    idx_precio = layout['idx_precio']
                    idx_desc = layout['idx_desc']
                    idx_recargo = layout['idx_recargo']

                    for fila in filas_datos:
                        if not fila or len(fila) <= max(idx_iva, idx_pct):
                            continue
                        try:
                            val_iva = self.limpiar_monto(str(fila[idx_iva] or ''))
                            val_pct = self.limpiar_monto(str(fila[idx_pct] or ''))
                        except Exception:
                            continue

                        def _celda(idx):
                            return self.limpiar_monto(str(fila[idx] or '')) if idx is not None and idx < len(fila) else None

                        cantidad = _celda(idx_cant)
                        precio_venta = _celda(idx_precio_venta)
                        precio_unit = _celda(idx_precio)
                        descuento = _celda(idx_desc) or 0
                        recargo = _celda(idx_recargo) or 0

                        # Confirmado con PDF real (factura FE-11275, 2026-09-05):
                        # pese al nombre "Precio unitario de venta", esa columna
                        # YA es el TOTAL neto de la línea (base gravable), no un
                        # precio por unidad — NO se multiplica por Cantidad.
                        # "Precio unitario" sí es genuinamente por unidad, pero
                        # viene CON IVA incluido (bruto); Precio unitario×Cantidad
                        # −Descuento+Recargo da el BRUTO de línea, y restarle el
                        # IVA ya reportado (valor literal del PDF, sin dividir
                        # entre la tarifa) da el mismo neto que la columna venta.
                        # Verificado exacto al centavo en 4 líneas de FE-11275
                        # con cantidades 1/10/10/13 y tarifas 5%/19%.
                        base_unit = None
                        if cantidad is not None and precio_unit is not None:
                            bruto_linea = (precio_unit * cantidad) - descuento + recargo
                            base_unit = bruto_linea - val_iva
                        base_venta = precio_venta

                        # Valor derivado del IVA — SOLO como referencia para
                        # decidir cuál columna de precio es la neta cuando hay
                        # ambigüedad; nunca se usa como base final (introduce
                        # redondeo, ver arriba).
                        base_ref = (val_iva / (val_pct / 100.0)) if (val_pct > 0 and val_iva > 0) else None

                        # Candidatos disponibles para esta línea (se conserva
                        # el ORDEN unit-primero para el caso sin referencia:
                        # mantiene el comportamiento histórico cuando no hay
                        # IVA con qué comparar, ej. líneas al 0%).
                        candidatos = []
                        if base_unit is not None:
                            candidatos.append(('unit', base_unit))
                        if base_venta is not None:
                            candidatos.append(('venta', base_venta))

                        if base_ref is not None and candidatos:
                            # SIEMPRE se compara contra IVA÷% cuando hay tarifa
                            # (no solo cuando unit y venta discrepan entre sí):
                            # una plantilla puede tener "Precio unitario" CON
                            # IVA en TODAS sus líneas gravadas — ahí unit y
                            # venta discrepan muchísimo entre sí, pero eso ya
                            # se detecta igual al comparar cada uno contra la
                            # referencia, sin necesitar ese chequeo previo.
                            nombre_elegido, base_linea = min(candidatos, key=lambda t: abs(t[1] - base_ref))
                            if len(candidatos) > 1:
                                otro_nombre, otro_valor = next(t for t in candidatos if t[0] != nombre_elegido)
                                if abs(otro_valor - base_linea) > 3:
                                    log(99, f"↪ Línea con precio ambiguo en factura "
                                            f"{datos.get('Numero_Factura', '?')}: se tomó columna "
                                            f"'{nombre_elegido}' ({base_linea:,.2f}) sobre '{otro_nombre}' "
                                            f"({otro_valor:,.2f}) por ser la más cercana a IVA÷%="
                                            f"{base_ref:,.2f} (IVA={val_iva:,.2f}, %={val_pct:g}). "
                                            f"Fila: {fila}", "WARN")
                            tolerancia = max(3, abs(base_ref) * 0.02)
                            if abs(base_linea - base_ref) > tolerancia:
                                log(99, f"⚠️ Ninguna columna de precio coincide con IVA÷%="
                                        f"{base_ref:,.2f} en esta línea (unit={base_unit}, "
                                        f"venta={base_venta}, IVA={val_iva}, %={val_pct}) — factura "
                                        f"{datos.get('Numero_Factura', '?')}, revisar plantilla/columnas. "
                                        f"Fila: {fila}", "WARN")
                        elif candidatos:
                            base_linea = candidatos[0][1]
                        elif base_ref is not None:
                            base_linea = base_ref
                        else:
                            base_linea = None

                        if val_iva <= 0 and (base_linea is None or base_linea <= 0):
                            continue

                        if abs(val_pct - 19) < 1:
                            iva_19 += val_iva
                            if base_linea is not None: base_19 += base_linea
                            encontrado = True
                        elif abs(val_pct - 5) < 1:
                            iva_5 += val_iva
                            if base_linea is not None: base_5 += base_linea
                            encontrado = True
                        elif base_linea is not None and base_linea > 0:
                            # Sin IVA (0/blank): exento y excluido no se distinguen desde
                            # el PDF (solo el XML lo permite) — un solo balde por ahora.
                            base_0 += base_linea
                            encontrado = True

                        if base_linea is None:
                            filas_debug.append(fila)

                        total_filas_leidas += 1
                        filas_pagina += 1

                if filas_pagina:
                    paginas_con_filas += 1

            except Exception:
                continue

        datos['_iva_tabla_encontrada'] = encontrado

        if encontrado:
            datos['IVA_19'] = self._validar_monto(iva_19)
            datos['IVA_5']  = self._validar_monto(iva_5)
            datos['Base_19'] = self._validar_monto(base_19)
            datos['Base_5']  = self._validar_monto(base_5)
            datos['Base_0']  = self._validar_monto(base_0)
            datos['Total_Base'] = self._validar_monto(base_19 + base_5 + base_0)
            log(99, f"✓ Detalles de Productos: {total_filas_leidas} filas leídas "
                    f"en {paginas_con_filas} página(s) — factura "
                    f"{datos.get('Numero_Factura', '?')}", "DEBUG")
            log(99, f"✓ IVA tabla: 19%={iva_19:,.0f} (base {base_19:,.0f}) / "
                    f"5%={iva_5:,.0f} (base {base_5:,.0f}) / base 0%={base_0:,.0f}", "DEBUG")

        for fila in filas_debug:
            log(99, f"⚠️ Fila de 'Detalles de Productos' sin Cantidad/Precio detectable "
                    f"(Factura {datos.get('Numero_Factura', '?')}): {fila}", "WARN")

    def _calcular_cuadre_iva(self, datos):
        """
        Verifica el dato ya extraído (NO recalcula la base ni el IVA):
          1) Total_Base (suma de bases por tarifa) debe cuadrar con el
             Subtotal reportado en 'Datos Totales'.
          2) Por cada tarifa con base > 0, base × tarifa% debe cuadrar con
             el valor de IVA de esa tarifa ya sumado desde la tabla.

        Un descuento/recargo GLOBAL (bloque Totales, no atado a una tarifa)
        hace que 1) no cuadre exacto — es intencional: se marca 'Revisar'
        en vez de repartir el ajuste a la fuerza entre tarifas.
        """
        if not datos.get('_iva_tabla_encontrada'):
            datos['Cuadre_IVA'] = ''  # sin tabla de detalle, nada que verificar
            return

        TOLERANCIA = 3  # pesos — margen de redondeo esperado

        problemas = []

        subtotal = datos.get('Subtotal', 0)
        total_base = datos.get('Total_Base', 0)
        if subtotal and abs(total_base - subtotal) > TOLERANCIA:
            problemas.append(f"Total Base ({total_base:,.0f}) ≠ Subtotal ({subtotal:,.0f})")

        if datos.get('Base_19', 0) > 0:
            esperado = datos['Base_19'] * 0.19
            if abs(esperado - datos.get('IVA_19', 0)) > TOLERANCIA:
                problemas.append(f"Base 19% × 19% ({esperado:,.0f}) ≠ IVA 19% ({datos.get('IVA_19', 0):,.0f})")

        if datos.get('Base_5', 0) > 0:
            esperado = datos['Base_5'] * 0.05
            if abs(esperado - datos.get('IVA_5', 0)) > TOLERANCIA:
                problemas.append(f"Base 5% × 5% ({esperado:,.0f}) ≠ IVA 5% ({datos.get('IVA_5', 0):,.0f})")

        if problemas:
            datos['Cuadre_IVA'] = 'Revisar'
            log(99, f"⚠️ Cuadre IVA a revisar (Factura {datos.get('Numero_Factura', '?')}): "
                    + " | ".join(problemas), "WARN")
        else:
            datos['Cuadre_IVA'] = 'OK'

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
            'IVA_19': [
                r'(?:^|\n)\s*IVA\s+19\s*%?\s+([\d\.,]+)',
                r'(?:^|\n)\s*IVA\s+19\s*%?\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Impuesto\s+19\s*%\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'IVA\s*\(19%?\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
            ],
            'IVA_5': [
                r'(?:^|\n)\s*IVA\s+5\s*%?\s+([\d\.,]+)',
                r'(?:^|\n)\s*IVA\s+5\s*%?\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'Impuesto\s+5\s*%\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
                r'IVA\s*\(5%?\)\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)',
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

def extraer_datos_pdf(ruta_pdf, cufe_original, numero, tipo_documento=None, password=None):
    extractor = ExtractorPDF()
    return extractor.extraer_datos(ruta_pdf, cufe_original, numero, tipo_documento, password=password)