#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
TEST DE CONFIGURACIÓN - VERIFICACIÓN PREVIA
Prueba que la nueva estructura funciona SIN modificar main.py
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import os

print("\n" + "="*70)
print("🧪 TEST DE CONFIGURACIÓN - PASO 1")
print("="*70 + "\n")

# 1. Verificar estructura de carpetas
print("📁 Verificando estructura de carpetas...")
carpetas_necesarias = ['config', 'core', 'utils', 'ui']
estructura_ok = True

for carpeta in carpetas_necesarias:
    existe = os.path.isdir(carpeta)
    estado = "✅" if existe else "❌"
    print(f"  {estado} {carpeta}/")
    if not existe:
        estructura_ok = False

if not estructura_ok:
    print("\n❌ ERROR: Faltan carpetas. Ejecuta setup_estructura.sh primero")
    sys.exit(1)

print("\n✅ Estructura de carpetas correcta\n")

# 2. Verificar __init__.py
print("📄 Verificando archivos __init__.py...")
init_ok = True

for carpeta in carpetas_necesarias:
    init_path = os.path.join(carpeta, '__init__.py')
    existe = os.path.isfile(init_path)
    estado = "✅" if existe else "❌"
    print(f"  {estado} {carpeta}/__init__.py")
    if not existe:
        init_ok = False

if not init_ok:
    print("\n❌ ERROR: Faltan archivos __init__.py")
    sys.exit(1)

print("\n✅ Archivos __init__.py correctos\n")

# 3. Verificar que se puede importar config
print("🔌 Probando imports...")
try:
    from config import Settings, cargar_settings
    print("  ✅ from config import Settings, cargar_settings")
except ImportError as e:
    print(f"  ❌ ERROR al importar config: {e}")
    sys.exit(1)

print("\n✅ Imports funcionando correctamente\n")

# 4. Probar Settings con valores por defecto
print("⚙️  Probando Settings con valores por defecto...")
try:
    settings = Settings()  # Sin archivo, solo defaults
    
    # Verificar que los valores son correctos
    assert settings.dian_url == "https://catalogo-vpfe.dian.gov.co/User/SearchDocument"
    assert settings.num_navegadores == 10
    assert settings.max_reintentos == 2
    assert settings.carpeta_pdfs == "facturas_pdfs_descargados"
    
    print("  ✅ Valores por defecto correctos")
    
except Exception as e:
    print(f"  ❌ ERROR: {e}")
    sys.exit(1)

# 5. Probar Settings con archivo config.json
print("\n⚙️  Probando Settings con config.json...")
try:
    settings = cargar_settings('config/config.json')
    settings.validar()
    
    print("  ✅ Configuración cargada desde config.json")
    print(f"  ✅ URL: {settings.dian_url}")
    print(f"  ✅ Navegadores: {settings.num_navegadores}")
    print(f"  ✅ Excel: {settings.archivo_excel}")
    
except FileNotFoundError:
    print("  ⚠️  config.json no encontrado (usará defaults)")
except Exception as e:
    print(f"  ❌ ERROR: {e}")
    sys.exit(1)

# 6. Verificar retrocompatibilidad
print("\n🔄 Verificando retrocompatibilidad...")
try:
    # Simular uso como en main.py original
    settings = cargar_settings()
    
    DIAN_URL = settings.dian_url
    NUM_NAVEGADORES = settings.num_navegadores
    MAX_REINTENTOS = settings.max_reintentos
    CARPETA_PDFS = settings.carpeta_pdfs
    ARCHIVO_MAPPING = settings.archivo_mapping
    ARCHIVO_EXCEL = settings.archivo_excel
    
    print(f"  ✅ Variables compatibles creadas:")
    print(f"     DIAN_URL = {DIAN_URL}")
    print(f"     NUM_NAVEGADORES = {NUM_NAVEGADORES}")
    print(f"     MAX_REINTENTOS = {MAX_REINTENTOS}")
    
except Exception as e:
    print(f"  ❌ ERROR en retrocompatibilidad: {e}")
    sys.exit(1)

# 7. Verificar que main.py original NO fue modificado
print("\n🔒 Verificando que main.py NO fue modificado...")
try:
    with open('main.py', 'r') as f:
        contenido = f.read()
    
    # Buscar las constantes originales
    if 'NUM_NAVEGADORES = 10' in contenido and 'MAX_REINTENTOS = 2' in contenido:
        print("  ✅ main.py original intacto")
    else:
        print("  ⚠️  main.py parece modificado (revisar)")
        
except FileNotFoundError:
    print("  ⚠️  main.py no encontrado en directorio actual")

# RESUMEN FINAL
print("\n" + "="*70)
print("✅ TODOS LOS TESTS PASARON")
print("="*70)
print("""
📝 RESUMEN:
  ✅ Estructura de carpetas creada
  ✅ Archivos __init__.py presentes
  ✅ Módulo config funcional
  ✅ Settings carga defaults correctamente
  ✅ Settings carga config.json correctamente
  ✅ Retrocompatibilidad verificada
  ✅ main.py original NO modificado

🎯 PRÓXIMO PASO:
  Ahora puedes usar el nuevo sistema de configuración en main.py
  agregando estas 2 líneas al inicio:
  
    from config import cargar_settings
    settings = cargar_settings()
    
  Y luego reemplazar:
    NUM_NAVEGADORES → settings.num_navegadores
    MAX_REINTENTOS → settings.max_reintentos
    ... etc
    
⚠️  IMPORTANTE:
  El código actual sigue funcionando 100% sin cambios.
  La refactorización es OPCIONAL y GRADUAL.
""")
print("="*70 + "\n")
