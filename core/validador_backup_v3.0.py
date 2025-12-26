"""
═══════════════════════════════════════════════════════════════════════════
VALIDADOR DE CUFES - CUFE DIAN AUTOMATION
Valida formato, elimina duplicados y detecta CUFEs inválidos
═══════════════════════════════════════════════════════════════════════════
"""

import os
import re
from typing import List, Tuple, Dict
from utils import log


class ValidadorCUFE:
    """
    Validador de CUFEs con detección de errores
    
    Validaciones:
    - Longitud correcta (96 caracteres)
    - Formato hexadecimal válido
    - Eliminación de duplicados
    - Archivo de entrada existe
    """
    
    LONGITUD_CUFE = 96
    
    def __init__(self):
        """Inicializa el validador"""
        self.cufes_validos = []
        self.cufes_invalidos = []
        self.duplicados_eliminados = 0
    
    def validar_archivo(self, ruta_archivo: str) -> Tuple[bool, str]:
        """
        Valida que el archivo existe y es legible
        
        Args:
            ruta_archivo: Ruta del archivo de CUFEs
            
        Returns:
            (existe, mensaje_error)
        """
        if not os.path.exists(ruta_archivo):
            return False, f"❌ Archivo no encontrado: {ruta_archivo}"
        
        if not os.path.isfile(ruta_archivo):
            return False, f"❌ No es un archivo: {ruta_archivo}"
        
        if not os.access(ruta_archivo, os.R_OK):
            return False, f"❌ Sin permisos de lectura: {ruta_archivo}"
        
        return True, ""
    
    def es_cufe_valido(self, cufe: str) -> Tuple[bool, str]:
        """
        Valida que un CUFE tenga formato correcto
        
        Args:
            cufe: CUFE a validar
            
        Returns:
            (es_valido, razon_si_invalido)
        """
        if not cufe:
            return False, "vacío"
        
        # Verificar longitud
        if len(cufe) != self.LONGITUD_CUFE:
            return False, f"longitud incorrecta ({len(cufe)} chars, esperados {self.LONGITUD_CUFE})"
        
        # Verificar que sea hexadecimal (solo letras a-f y números 0-9)
        if not re.match(r'^[a-fA-F0-9]+$', cufe):
            return False, "formato no hexadecimal"
        
        return True, ""
    
    def cargar_y_validar(self, ruta_archivo: str) -> Tuple[List[str], Dict[str, any]]:
        """
        Carga y valida CUFEs desde archivo
        
        Args:
            ruta_archivo: Ruta del archivo de entrada
            
        Returns:
            (lista_cufes_validos, estadisticas)
        """
        # Validar archivo
        existe, error = self.validar_archivo(ruta_archivo)
        if not existe:
            log(0, error, "ERROR")
            return [], {'error': error}
        
        # Leer archivo
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                lineas = [l.strip() for l in f if l.strip()]
        except Exception as e:
            error = f"❌ Error leyendo archivo: {str(e)}"
            log(0, error, "ERROR")
            return [], {'error': error}
        
        if not lineas:
            error = "❌ Archivo vacío"
            log(0, error, "ERROR")
            return [], {'error': error}
        
        # Validar cada CUFE
        cufes_vistos = set()
        self.cufes_validos = []
        self.cufes_invalidos = []
        self.duplicados_eliminados = 0
        
        for idx, cufe in enumerate(lineas, 1):
            # Verificar duplicados
            if cufe in cufes_vistos:
                self.duplicados_eliminados += 1
                log(0, f"⚠️  CUFE #{idx} duplicado (ignorado)", "WARN")
                continue
            
            # Validar formato
            es_valido, razon = self.es_cufe_valido(cufe)
            
            if es_valido:
                self.cufes_validos.append(cufe)
                cufes_vistos.add(cufe)
            else:
                self.cufes_invalidos.append({
                    'linea': idx,
                    'cufe': cufe[:20] + '...' if len(cufe) > 20 else cufe,
                    'razon': razon
                })
                log(0, f"⚠️  CUFE #{idx} inválido: {razon}", "WARN")
        
        # Estadísticas
        stats = {
            'total_lineas': len(lineas),
            'validos': len(self.cufes_validos),
            'invalidos': len(self.cufes_invalidos),
            'duplicados': self.duplicados_eliminados
        }
        
        # Mostrar resumen
        self._mostrar_resumen(stats)
        
        return self.cufes_validos, stats
    
    def _mostrar_resumen(self, stats: Dict):
        """Muestra resumen de validación"""
        print("\n" + "="*70)
        print("📋 VALIDACIÓN DE CUFEs")
        print("="*70)
        
        log(0, f"📄 Total líneas: {stats['total_lineas']}", "INFO")
        log(0, f"✅ CUFEs válidos: {stats['validos']}", "OK")
        
        if stats['duplicados'] > 0:
            log(0, f"🔄 Duplicados eliminados: {stats['duplicados']}", "WARN")
        
        if stats['invalidos'] > 0:
            log(0, f"❌ CUFEs inválidos: {stats['invalidos']}", "ERROR")
            
            # Mostrar primeros 5 inválidos
            for item in self.cufes_invalidos[:5]:
                log(0, f"   Línea {item['linea']}: {item['razon']}", "ERROR")
            
            if len(self.cufes_invalidos) > 5:
                log(0, f"   ... y {len(self.cufes_invalidos) - 5} más", "ERROR")
        
        print("="*70 + "\n")
        
        # Si no hay CUFEs válidos, es un error crítico
        if stats['validos'] == 0:
            log(0, "❌ No hay CUFEs válidos para procesar", "CRIT")
            return False
        
        return True


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIÓN DE CONVENIENCIA (compatibilidad con código original)
# ═══════════════════════════════════════════════════════════════════════════

def cargar_cufes(ruta_archivo: str) -> List[str]:
    """
    Función wrapper para mantener compatibilidad con código original
    
    Args:
        ruta_archivo: Ruta del archivo de CUFEs
        
    Returns:
        Lista de CUFEs válidos
    """
    validador = ValidadorCUFE()
    cufes, stats = validador.cargar_y_validar(ruta_archivo)
    
    # Si hay errores críticos, retornar lista vacía
    if stats.get('error') or stats.get('validos', 0) == 0:
        return []
    
    return cufes


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 PROBANDO VALIDADOR DE CUFEs")
    print("="*70 + "\n")
    
    import sys
    
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
        print(f"📄 Validando: {archivo}\n")
        
        cufes = cargar_cufes(archivo)
        
        print(f"\n✅ Resultado: {len(cufes)} CUFEs válidos listos para procesar")
    else:
        print("ℹ️  Uso: python3 -m core.validador <archivo_cufes.txt>")
        
        # Test con datos de ejemplo
        print("\n🧪 Test con CUFEs de ejemplo:\n")
        
        # Crear archivo temporal de prueba
        with open('/tmp/test_cufes.txt', 'w') as f:
            f.write("8d528789cb2547d090fcae2acccfc04e8588a8b80ea7de7bda94ff33c11a0ccf564fa6c73c49ca8ca43809557eaa3a3a\n")  # Válido
            f.write("8d528789cb2547d090fcae2acccfc04e8588a8b80ea7de7bda94ff33c11a0ccf564fa6c73c49ca8ca43809557eaa3a3a\n")  # Duplicado
            f.write("INVALIDO123\n")  # Inválido (muy corto)
            f.write("gggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggg\n")  # Inválido (g no es hex)
            f.write("c64601b7a5b65b68d2ff2a7e7c31d48beb674bc0974172368193825144d5aa5c1d7d444412ae5fbc7819e3e70341bc71\n")  # Válido
        
        cufes = cargar_cufes('/tmp/test_cufes.txt')
        print(f"\n✅ {len(cufes)} CUFEs válidos encontrados")
    
    print("\n" + "="*70 + "\n")
