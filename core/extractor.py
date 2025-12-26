"""
═══════════════════════════════════════════════════════════════════════════
EXTRACTOR DE DATOS PDF - CUFE DIAN AUTOMATION
Extrae información estructurada de facturas electrónicas en PDF
═══════════════════════════════════════════════════════════════════════════
"""

import os
import re
import pdfplumber
from utils import log


class ExtractorPDF:
    """
    Extractor de datos de facturas electrónicas en PDF
    
    Extrae:
    - Información del emisor (NIT, razón social, dirección, etc.)
    - Información del receptor/adquiriente
    - Datos de la factura (número, fechas, CUFE)
    - Información financiera (subtotal, IVA, total)
    - Métodos de pago
    """
    
    def __init__(self):
        """Inicializa el extractor"""
        pass
    
    @staticmethod
    def limpiar_texto(texto):
        """
        Limpia texto eliminando espacios múltiples
        
        Args:
            texto: Texto a limpiar
            
        Returns:
            Texto limpio
        """
        if not texto:
            return ""
        return re.sub(r'\s+', ' ', texto).strip()
    
    @staticmethod
    def limpiar_nit(texto):
        """
        Extrae solo los números del NIT
        
        Args:
            texto: Texto que contiene el NIT
            
        Returns:
            NIT limpio (solo números, puntos y guiones)
        """
        if not texto:
            return ""
        match = re.search(r'([\d\.-]+)', texto)
        return match.group(1) if match else texto
    
    def extraer_datos(self, ruta_pdf, cufe_original, numero):
        """
        Extrae todos los datos del PDF
        
        Args:
            ruta_pdf: Ruta del archivo PDF
            cufe_original: CUFE original usado para descargar
            numero: Número secuencial del CUFE
            
        Returns:
            Diccionario con todos los datos extraídos
        """
        datos = {
            'Numero': numero,
            'CUFE': cufe_original,
            'Numero_Factura': '',
            'Prefijo': '',
            'Folio': '',
            'Fecha_Emision': '',
            'Fecha_Vencimiento': '',
            'Forma_Pago': '',
            'Medio_Pago': '',
            'Emisor_RazonSocial': '',
            'Emisor_NIT': '',
            'Emisor_Direccion': '',
            'Emisor_Ciudad': '',
            'Emisor_Departamento': '',
            'Emisor_Telefono': '',
            'Emisor_Email': '',
            'Receptor_RazonSocial': '',
            'Receptor_NIT': '',
            'Receptor_Direccion': '',
            'Receptor_Ciudad': '',
            'Receptor_Departamento': '',
            'Receptor_Email': '',
            'Subtotal': '',
            'IVA': '',
            'Total_Factura': '',
            'Numero_Autorizacion': '',
            'Ruta_PDF': os.path.abspath(ruta_pdf),
            'Notas': '',
            'Estado': '✅ Procesado'
        }
        
        try:
            with pdfplumber.open(ruta_pdf) as pdf:
                # Extraer texto completo
                texto_completo = ""
                for pagina in pdf.pages:
                    texto_completo += pagina.extract_text() + "\n"
                
                # Extraer cada campo
                self._extraer_cufe(datos, texto_completo)
                self._extraer_numero_factura(datos, texto_completo)
                self._extraer_fechas(datos, texto_completo)
                self._extraer_emisor(datos, texto_completo)
                self._extraer_receptor(datos, texto_completo)
                self._extraer_financiero(datos, texto_completo)
                self._extraer_pagos(datos, texto_completo)
                self._extraer_autorizacion(datos, texto_completo)
        
        except Exception as e:
            log(99, f"Error extrayendo: {str(e)[:40]}", "ERROR")
            datos['Estado'] = '❌ Error'
        
        return datos
    
    def _extraer_cufe(self, datos, texto):
        """Extrae el CUFE del texto"""
        m = re.search(r'CUFE\s*:?\s*([\w\n]+)', texto)
        if m:
            datos['CUFE'] = m.group(1).replace('\n', '').strip()
    
    def _extraer_numero_factura(self, datos, texto):
        """Extrae número de factura, prefijo y folio"""
        m = re.search(r'Número de Factura:\s*([A-Z0-9\-]+)', texto)
        if m:
            numero_factura = m.group(1)
            datos['Numero_Factura'] = numero_factura
            
            # Separar prefijo y folio
            partes = numero_factura.split('-')
            if len(partes) == 2:
                datos['Prefijo'] = partes[0]
                datos['Folio'] = partes[1]
    
    def _extraer_fechas(self, datos, texto):
        """Extrae fechas de emisión y vencimiento"""
        m = re.search(r'Fecha de Emisión:\s*(\d{2}/\d{2}/\d{4})', texto)
        if m:
            datos['Fecha_Emision'] = m.group(1)
        
        m = re.search(r'Fecha de Vencimiento:\s*(\d{2}/\d{2}/\d{4})', texto)
        if m:
            datos['Fecha_Vencimiento'] = m.group(1)
    
    def _extraer_emisor(self, datos, texto):
        """Extrae datos del emisor"""
        # Buscar bloque del emisor
        bloque_emisor = re.search(
            r'Datos del Emisor.*?Datos del Adquiriente',
            texto,
            re.DOTALL | re.IGNORECASE
        )
        txt_emisor = bloque_emisor.group(0) if bloque_emisor else texto
        
        # Razón social
        m = re.search(r'Razón Social:\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_RazonSocial'] = self.limpiar_texto(m.group(1))
        
        # NIT
        m = re.search(r'Nit del Emisor:\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_NIT'] = self.limpiar_nit(m.group(1))
        
        # Dirección
        m = re.search(r'Dirección:\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_Direccion'] = self.limpiar_texto(m.group(1))
        
        # Ciudad
        m = re.search(r'Ciudad:\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_Ciudad'] = self.limpiar_texto(m.group(1))
        
        # Departamento
        m = re.search(r'Departamento:\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_Departamento'] = self.limpiar_texto(m.group(1))
        
        # Teléfono
        m = re.search(r'(?:Teléfono|Telefono):\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_Telefono'] = self.limpiar_texto(m.group(1))
        
        # Email
        m = re.search(r'Email:\s*([^\n]+)', txt_emisor)
        if m:
            datos['Emisor_Email'] = self.limpiar_texto(m.group(1))
    
    def _extraer_receptor(self, datos, texto):
        """Extrae datos del receptor/adquiriente"""
        # Buscar bloque del receptor
        bloque_receptor = re.search(
            r'Datos del Adquiriente.*?(?:Detalles de Productos|Observaciones)',
            texto,
            re.DOTALL | re.IGNORECASE
        )
        
        if not bloque_receptor:
            return
        
        txt_receptor = bloque_receptor.group(0)
        
        # Razón social
        m = re.search(r'(?:Nombre o )?Razón Social:\s*([^\n]+)', txt_receptor)
        if m:
            datos['Receptor_RazonSocial'] = self.limpiar_texto(m.group(1))
        
        # NIT/Documento
        m = re.search(r'Número Documento:\s*([^\n]+)', txt_receptor)
        if m:
            datos['Receptor_NIT'] = self.limpiar_nit(m.group(1))
        
        # Dirección
        m = re.search(r'Dirección:\s*([^\n]+)', txt_receptor)
        if m:
            datos['Receptor_Direccion'] = self.limpiar_texto(m.group(1))
        
        # Ciudad
        m = re.search(r'Ciudad:\s*([^\n]+)', txt_receptor)
        if m:
            datos['Receptor_Ciudad'] = self.limpiar_texto(m.group(1))
        
        # Departamento
        m = re.search(r'Departamento:\s*([^\n]+)', txt_receptor)
        if m:
            datos['Receptor_Departamento'] = self.limpiar_texto(m.group(1))
        
        # Email
        m = re.search(r'Email:\s*([^\n]+)', txt_receptor)
        if m:
            datos['Receptor_Email'] = self.limpiar_texto(m.group(1))
    
    def _extraer_financiero(self, datos, texto):
        """Extrae información financiera (subtotal, IVA, total)"""
        # Total factura
        m = re.search(r'Total factura.*?(?:COP\s+)?\$?\s*([\d\.,]+)', texto)
        if m:
            datos['Total_Factura'] = m.group(1)
        
        # Subtotal
        m = re.search(r'Subtotal\s*[\n\r]*\s*(?:COP)?\s*\$?\s*([\d\.,]+)', texto)
        if m:
            datos['Subtotal'] = m.group(1)
        
        # IVA
        m = re.search(r'Total impuesto.*?(=).*?([\d\.,]+)', texto, re.DOTALL)
        if not m:
            m = re.search(r'(?:^|\n)IVA\s+([\d,\.]+)', texto)
        if m:
            datos['IVA'] = m.group(2) if len(m.groups()) > 1 else m.group(1)
    
    def _extraer_pagos(self, datos, texto):
        """Extrae forma y medio de pago"""
        # Forma de pago
        m = re.search(r'Forma de pago:\s*([^\n]+)', texto)
        if m:
            datos['Forma_Pago'] = self.limpiar_texto(m.group(1))
        
        # Medio de pago
        m = re.search(r'Medio de Pago:\s*([^\n]+)', texto)
        if m:
            datos['Medio_Pago'] = self.limpiar_texto(m.group(1))
    
    def _extraer_autorizacion(self, datos, texto):
        """Extrae número de autorización"""
        m = re.search(r'Numero de Autorización:\s*(\d+)', texto)
        if m:
            datos['Numero_Autorizacion'] = m.group(1)


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIÓN DE CONVENIENCIA (compatibilidad con código original)
# ═══════════════════════════════════════════════════════════════════════════

def extraer_datos_pdf(ruta_pdf, cufe_original, numero):
    """
    Función wrapper para mantener compatibilidad con código original
    
    Args:
        ruta_pdf: Ruta del archivo PDF
        cufe_original: CUFE original
        numero: Número secuencial
        
    Returns:
        Diccionario con datos extraídos
    """
    extractor = ExtractorPDF()
    return extractor.extraer_datos(ruta_pdf, cufe_original, numero)


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 PROBANDO EXTRACTOR DE PDF")
    print("="*70 + "\n")
    
    # Probar con un PDF de ejemplo (si existe)
    import sys
    if len(sys.argv) > 1:
        ruta_pdf = sys.argv[1]
        print(f"📄 Extrayendo datos de: {ruta_pdf}\n")
        
        datos = extraer_datos_pdf(ruta_pdf, "TEST_CUFE", 1)
        
        print("✅ Datos extraídos:")
        for clave, valor in datos.items():
            if valor:  # Solo mostrar campos con datos
                print(f"  • {clave}: {valor}")
    else:
        print("ℹ️  Uso: python3 extractor.py <ruta_pdf>")
    
    print("\n" + "="*70 + "\n")