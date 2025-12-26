"""
═══════════════════════════════════════════════════════════════════════════
GESTOR DE CONFIGURACIÓN - CUFE DIAN AUTOMATION
Carga y valida configuración desde config.json
RETROCOMPATIBLE: Funciona con o sin archivo de configuración
═══════════════════════════════════════════════════════════════════════════
"""

import json
import os
from pathlib import Path
from datetime import datetime


class Settings:
    """Gestor centralizado de configuración con valores por defecto"""
    
    def __init__(self, config_path=None):
        """
        Inicializa configuración
        
        Args:
            config_path: Ruta al archivo config.json (opcional)
        """
        self._config = self._cargar_defaults()
        
        if config_path and os.path.exists(config_path):
            self._cargar_desde_archivo(config_path)
    
    def _cargar_defaults(self):
        """Valores por defecto - IDÉNTICOS al main.py original"""
        return {
            'dian': {
                'url': "https://catalogo-vpfe.dian.gov.co/User/SearchDocument",
                'timeout_carga_pagina': 30,
                'timeout_descarga_pdf': 60
            },
            'navegadores': {
                'cantidad_paralela': 10,
                'headless': False,
                'user_agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            'descarga': {
                'max_reintentos': 2,
                'carpeta_pdfs': "facturas_pdfs_descargados",
                'archivo_mapping': "mapping_cufes_pdfs.json",
                'archivo_checkpoint': "checkpoint_descarga.json"
            },
            'excel': {
                'prefijo_archivo': "Facturas_Completas",
                'incluir_timestamp': True,
                'formato_fecha': "%Y%m%d_%H%M%S"
            },
            'logs': {
                'nivel': 'INFO',
                'guardar_archivo': False,
                'archivo_log': "cufe_automation.log",
                'colores': {
                    "INFO": "\033[94m",
                    "OK": "\033[92m",
                    "WARN": "\033[93m",
                    "ERROR": "\033[91m",
                    "DEBUG": "\033[96m",
                    "CRIT": "\033[95m",
                    "EXCEL": "\033[93m",
                    "RETRY": "\033[95m"
                }
            },
            'validaciones': {
                'longitud_cufe': 96,
                'verificar_formato_hex': True,
                'eliminar_duplicados': True
            }
        }
    
    def _cargar_desde_archivo(self, config_path):
        """Carga configuración desde JSON"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_usuario = json.load(f)
            
            # Merge: mantener defaults y sobrescribir con valores del usuario
            self._merge_config(self._config, config_usuario)
            
        except Exception as e:
            print(f"⚠️  No se pudo cargar {config_path}: {e}")
            print("ℹ️  Usando configuración por defecto")
    
    def _merge_config(self, base, override):
        """Merge recursivo de configuraciones"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    # ═══════════════════════════════════════════════════════════════════════
    # PROPIEDADES - Acceso fácil a configuraciones
    # ═══════════════════════════════════════════════════════════════════════
    
    @property
    def dian_url(self):
        """URL del portal DIAN"""
        return self._config['dian']['url']
    
    @property
    def num_navegadores(self):
        """Cantidad de navegadores en paralelo"""
        return self._config['navegadores']['cantidad_paralela']
    
    @property
    def max_reintentos(self):
        """Máximo de reintentos por CUFE"""
        return self._config['descarga']['max_reintentos']
    
    @property
    def carpeta_pdfs(self):
        """Carpeta donde se guardan PDFs"""
        return self._config['descarga']['carpeta_pdfs']
    
    @property
    def archivo_mapping(self):
        """Archivo JSON de mapping CUFE->PDF"""
        return self._config['descarga']['archivo_mapping']
    
    @property
    def archivo_checkpoint(self):
        """Archivo JSON de checkpoint"""
        return self._config['descarga']['archivo_checkpoint']
    
    @property
    def archivo_excel(self):
        """Genera nombre de archivo Excel con timestamp"""
        config = self._config['excel']
        
        if config['incluir_timestamp']:
            timestamp = datetime.now().strftime(config['formato_fecha'])
            return f"{config['prefijo_archivo']}_{timestamp}.xlsx"
        else:
            return f"{config['prefijo_archivo']}.xlsx"
    
    @property
    def colores_log(self):
        """Diccionario de colores para logs"""
        return self._config['logs']['colores']
    
    @property
    def headless(self):
        """Modo headless de navegadores"""
        return self._config['navegadores']['headless']
    
    # ═══════════════════════════════════════════════════════════════════════
    # MÉTODOS DE UTILIDAD
    # ═══════════════════════════════════════════════════════════════════════
    
    def get(self, *keys, default=None):
        """
        Acceso seguro a configuración anidada
        
        Ejemplo:
            settings.get('dian', 'url')
            settings.get('navegadores', 'cantidad_paralela')
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def crear_carpetas(self):
        """Crea carpetas necesarias si no existen"""
        Path(self.carpeta_pdfs).mkdir(parents=True, exist_ok=True)
    
    def validar(self):
        """Valida que la configuración sea correcta"""
        errores = []
        
        # Validar URL
        if not self.dian_url.startswith('http'):
            errores.append("URL de DIAN inválida")
        
        # Validar números positivos
        if self.num_navegadores <= 0:
            errores.append("Cantidad de navegadores debe ser > 0")
        
        if self.max_reintentos < 0:
            errores.append("Max reintentos debe ser >= 0")
        
        if errores:
            raise ValueError(f"Configuración inválida: {', '.join(errores)}")
        
        return True
    
    def mostrar(self):
        """Muestra configuración actual (para debugging)"""
        print("\n" + "="*70)
        print("⚙️  CONFIGURACIÓN ACTUAL")
        print("="*70)
        print(json.dumps(self._config, indent=2, ensure_ascii=False))
        print("="*70 + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# INSTANCIA GLOBAL (opcional, para facilitar imports)
# ═══════════════════════════════════════════════════════════════════════════

def cargar_settings(config_path='config/config.json'):
    """
    Factory function para crear instancia de Settings
    
    Uso:
        from config.settings import cargar_settings
        settings = cargar_settings()
    """
    return Settings(config_path if os.path.exists(config_path) else None)


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧪 Probando gestor de configuración...\n")
    
    # Crear instancia
    settings = cargar_settings()
    
    # Validar
    settings.validar()
    print("✅ Validación exitosa")
    
    # Probar propiedades
    print(f"\n📊 Propiedades:")
    print(f"  • URL DIAN: {settings.dian_url}")
    print(f"  • Navegadores: {settings.num_navegadores}")
    print(f"  • Reintentos: {settings.max_reintentos}")
    print(f"  • Carpeta PDFs: {settings.carpeta_pdfs}")
    print(f"  • Archivo Excel: {settings.archivo_excel}")
    
    # Mostrar configuración completa
    settings.mostrar()
    
    print("✅ Test completado\n")
