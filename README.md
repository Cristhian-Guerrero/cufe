# 🎯 Sistema de Consulta CUFE - DIAN Colombia

Sistema automatizado para consultar y extraer información de facturas electrónicas del portal DIAN.

## 🚀 Instalación
```bash
pip install --user --break-system-packages -r requirements.txt
```

## 📝 Uso

1. Edita `cufes_test.txt` con los CUFEs a consultar (uno por línea)
2. Ejecuta:
```bash
   python3 sistema_cufe_final.py
```
3. Los resultados se guardan en:
   - Excel: `facturas_YYYYMMDD_HHMMSS.xlsx`
   - PDFs: `facturas_pdfs/`

## 📊 Campos Extraídos (33 campos)

- **Documento:** CUFE, Número, Fechas, Forma/Medio de Pago
- **Emisor:** Razón Social, NIT, Dirección, Contactos
- **Receptor:** Nombre, NIT, Dirección, Contactos
- **Productos:** Descripción, Cantidad, Precio
- **Totales:** Subtotal, IVA, Total
- **Autorización:** Número, Vigencia

## 🔗 Características

✅ Bypass automático de Cloudflare Turnstile
✅ Descarga automática de PDFs
✅ Extracción completa de datos con pdfplumber
✅ Excel con hyperlinks clickeables a PDFs
✅ Procesamiento masivo secuencial

## 📁 Estructura
```
cufe-dian-test/
├── sistema_cufe_final.py       ⭐ Script principal
├── CloudflareBypasser.py       🔧 Bypass Turnstile
├── cufes_test.txt             📝 CUFEs a procesar
├── requirements.txt           📦 Dependencias
├── facturas_pdfs/             📁 PDFs descargados
└── facturas_*.xlsx            📊 Resultados
```

## 🛠️ Solución de Problemas

**Turnstile no se resuelve:**
- El script lo intenta automáticamente
- Si falla, te pedirá click manual

**Hyperlinks no funcionan:**
- Verifica que los PDFs estén en `facturas_pdfs/`
- El Excel usa protocolo `file:///`

---

**Desarrollado para consultas masivas DIAN**
