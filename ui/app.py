"""
Sistema de Consulta CUFE DIAN - Interfaz Gráfica v4.3.0
Desarrollado por © C. Guerrero
Para: A.S. Contadores & Asesores SAS
Pasto, Nariño - Colombia
"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from PIL import Image, ImageTk

# Agregar el directorio padre al path para importar módulos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar módulos del sistema CUFE
try:
    from config import cargar_settings
    from core.orquestador import ejecutar_sistema
    from core.validador import cargar_cufes
    from core.excel_generator import generar_excel_final
    MODULOS_DISPONIBLES = True
except ImportError as e:
    print(f"Aviso: Módulos no disponibles ({e}). Modo solo GUI.")
    MODULOS_DISPONIBLES = False

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE LA APLICACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

APP_CONFIG = {
    'title': 'Sistema de Consulta CUFE | A.S. Contadores & Asesores SAS',
    'version': '4.3.0',
    'company': 'A.S. Contadores & Asesores SAS',
    'location': 'Pasto, Nariño',
    'developer': '© C. Guerrero',
    'width': 850,
    'height': 620,
    'max_navegadores': 10,
}


class ConsultaCUFEApp(tk.Tk):
    """Interfaz Profesional para Consulta CUFE DIAN - v4.3.0"""
    
    def __init__(self):
        super().__init__()
        
        self.title(APP_CONFIG['title'])
        self.processing = False
        self.stop_requested = False
        
        # Colores modernos
        self.COLORS = {
            'primary': '#1B5E20',
            'primary_light': '#2E7D32',
            'primary_dark': '#0D3311',
            'accent': '#4CAF50',
            'background': '#FAFAFA',
            'surface': '#FFFFFF',
            'card': '#FFFFFF',
            'text_primary': '#212121',
            'text_secondary': '#757575',
            'text_light': '#FFFFFF',
            'success': '#2E7D32',
            'warning': '#F57C00',
            'error': '#D32F2F',
            'border': '#E0E0E0',
            'disabled': '#BDBDBD',
            'input_bg': '#F5F5F5',
        }
        
        self.FONTS = {
            'title': ('Segoe UI', 16, 'bold'),
            'subtitle': ('Segoe UI', 10),
            'section': ('Segoe UI', 9, 'bold'),
            'body': ('Segoe UI', 9),
            'button': ('Segoe UI', 9, 'bold'),
            'small': ('Segoe UI', 8),
            'log': ('Consolas', 8),
            'porcentaje': ('Segoe UI', 32, 'bold'),
        }
        
        # Variables de estado
        self.archivo_entrada = tk.StringVar(value="")
        self.carpeta_salida = tk.StringVar(value=os.path.expanduser("~"))
        self.lista_cufes = []
        self.cufes_validos = []
        self.cufes_invalidos = []
        self.duplicados = 0
        self.progreso_actual = 0
        self.total_procesar = 0
        self.resultado_final = None
        self.archivo_excel_generado = None
        
        self.log_queue = queue.Queue()
        
        # Configurar ventana
        self.geometry(f"{APP_CONFIG['width']}x{APP_CONFIG['height']}")
        self.minsize(APP_CONFIG['width'], APP_CONFIG['height'])
        self.resizable(False, False)
        self.configure(bg=self.COLORS['background'])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Cargar icono PRIMERO
        self.setup_icon()
        self.center_window()
        self.setup_styles()
        self.create_ui()
        self.process_log_queue()
    
    def resource_path(self, relative_path):
        """Obtiene ruta de recursos tanto en desarrollo como en .exe"""
        try:
            # PyInstaller crea una carpeta temporal
            base_path = sys._MEIPASS
        except AttributeError:
            # En desarrollo
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)
    
    def center_window(self):
        self.update_idletasks()
        width = APP_CONFIG['width']
        height = APP_CONFIG['height']
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2) - 30
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def setup_icon(self):
        """Configura el icono de la aplicación"""
        try:
            import platform
            
            # Intentar cargar dian.ico para Windows
            if platform.system() == "Windows":
                # Buscar en varias ubicaciones
                posibles_rutas = [
                    self.resource_path("assets/dian.ico"),
                    self.resource_path("dian.ico"),
                    os.path.join(os.path.dirname(__file__), "assets", "dian.ico"),
                    "assets/dian.ico",
                    "dian.ico",
                ]
                
                for icon_path in posibles_rutas:
                    if os.path.exists(icon_path):
                        try:
                            self.iconbitmap(default=icon_path)
                            print(f"Icono cargado: {icon_path}")
                            return
                        except Exception as e:
                            print(f"Error con {icon_path}: {e}")
                            continue
            
            # Fallback: usar logo.png como icono
            posibles_logos = [
                self.resource_path("assets/logo.png"),
                self.resource_path("logo.png"),
                os.path.join(os.path.dirname(__file__), "assets", "logo.png"),
            ]
            
            for logo_path in posibles_logos:
                if os.path.exists(logo_path):
                    try:
                        pil_image = Image.open(logo_path)
                        # Crear iconos de varios tamaños
                        icon_sizes = [(48, 48), (32, 32), (16, 16)]
                        icons = []
                        for size in icon_sizes:
                            resized = pil_image.resize(size, Image.Resampling.LANCZOS)
                            icons.append(ImageTk.PhotoImage(resized))
                        
                        self.iconphoto(True, *icons)
                        self._icon_refs = icons  # Mantener referencia
                        print(f"Logo como icono: {logo_path}")
                        return
                    except Exception as e:
                        print(f"Error con logo {logo_path}: {e}")
                        continue
                        
        except Exception as e:
            print(f"No se pudo cargar icono: {e}")
    
    def load_logo(self, max_width=250, max_height=50):
        """Carga el logo de la empresa"""
        posibles_logos = [
            self.resource_path("assets/logo.png"),
            self.resource_path("logo.png"),
            os.path.join(os.path.dirname(__file__), "assets", "logo.png"),
        ]
        
        for logo_path in posibles_logos:
            if os.path.exists(logo_path):
                try:
                    pil_image = Image.open(logo_path)
                    original_size = pil_image.size
                    
                    width_ratio = max_width / original_size[0]
                    height_ratio = max_height / original_size[1]
                    scale_ratio = min(width_ratio, height_ratio)
                    
                    if scale_ratio < 1:
                        new_size = (int(original_size[0] * scale_ratio), 
                                   int(original_size[1] * scale_ratio))
                        pil_resized = pil_image.resize(new_size, Image.Resampling.LANCZOS)
                        return ImageTk.PhotoImage(pil_resized)
                    else:
                        return ImageTk.PhotoImage(pil_image)
                except Exception as e:
                    print(f"Error cargando logo: {e}")
                    continue
        return None
    
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Frames
        self.style.configure('Header.TFrame', background=self.COLORS['primary'])
        self.style.configure('Main.TFrame', background=self.COLORS['background'])
        self.style.configure('Card.TFrame', background=self.COLORS['card'])
        self.style.configure('Footer.TFrame', background=self.COLORS['surface'])
        
        # Labels
        self.style.configure('Header.TLabel', background=self.COLORS['primary'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['title'])
        self.style.configure('HeaderSub.TLabel', background=self.COLORS['primary'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['subtitle'])
        self.style.configure('Section.TLabel', background=self.COLORS['card'],
                           foreground=self.COLORS['primary'], font=self.FONTS['section'])
        self.style.configure('Body.TLabel', background=self.COLORS['card'],
                           foreground=self.COLORS['text_primary'], font=self.FONTS['body'])
        self.style.configure('Small.TLabel', background=self.COLORS['surface'],
                           foreground=self.COLORS['text_secondary'], font=self.FONTS['small'])
        
        # LabelFrame
        self.style.configure('Card.TLabelframe', background=self.COLORS['card'],
                           borderwidth=1, relief='solid')
        self.style.configure('Card.TLabelframe.Label', background=self.COLORS['card'],
                           foreground=self.COLORS['primary'], font=self.FONTS['section'])
        
        # Buttons
        self.style.configure('Primary.TButton', font=self.FONTS['button'], padding=(12, 6))
        self.style.configure('Success.TButton', font=self.FONTS['button'], padding=(12, 6))
        self.style.configure('Danger.TButton', font=self.FONTS['button'], padding=(8, 5))
        self.style.configure('Secondary.TButton', font=self.FONTS['button'], padding=(8, 5))
    
    def create_ui(self):
        # Header
        self.create_header()
        
        # Main content
        main = ttk.Frame(self, style='Main.TFrame')
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        
        self.create_config_section(main)
        self.create_validation_bar(main)
        self.create_buttons_section(main)
        self.create_progress_section(main)
        self.create_log_section(main)
        
        # Footer
        self.create_footer()
    
    def create_header(self):
        header = tk.Frame(self, bg=self.COLORS['primary'], height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        content = tk.Frame(header, bg=self.COLORS['primary'])
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=8)
        
        # Logo
        logo = self.load_logo(max_width=220, max_height=45)
        if logo:
            self._logo_ref = logo
            logo_label = tk.Label(content, image=logo, bg=self.COLORS['primary'])
            logo_label.pack(side=tk.LEFT)
        else:
            company = tk.Label(content, text="A.S. CONTADORES", 
                              font=self.FONTS['title'], fg='white', bg=self.COLORS['primary'])
            company.pack(side=tk.LEFT)
        
        # Título
        title_frame = tk.Frame(content, bg=self.COLORS['primary'])
        title_frame.pack(side=tk.RIGHT)
        
        title = tk.Label(title_frame, text="Sistema de Consulta CUFE",
                        font=self.FONTS['title'], fg='white', bg=self.COLORS['primary'])
        title.pack(anchor='e')
        
        subtitle = tk.Label(title_frame, text="Facturación Electrónica DIAN",
                           font=self.FONTS['subtitle'], fg='#C8E6C9', bg=self.COLORS['primary'])
        subtitle.pack(anchor='e')
    
    def create_config_section(self, parent):
        frame = ttk.LabelFrame(parent, text=" Configuración ", style='Card.TLabelframe', padding=8)
        frame.pack(fill=tk.X, pady=(0, 6))
        
        # Entrada
        row1 = tk.Frame(frame, bg=self.COLORS['card'])
        row1.pack(fill=tk.X, pady=(0, 4))
        
        tk.Label(row1, text="Entrada:", font=self.FONTS['section'], width=8, anchor='w',
                bg=self.COLORS['card'], fg=self.COLORS['primary']).pack(side=tk.LEFT)
        
        self.entry_archivo = tk.Entry(row1, textvariable=self.archivo_entrada,
                                      font=self.FONTS['body'], state='readonly',
                                      bg=self.COLORS['input_bg'], relief='flat', bd=1)
        self.entry_archivo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        
        self.btn_seleccionar = tk.Button(row1, text="📂 Seleccionar", font=self.FONTS['button'],
                                        bg=self.COLORS['primary'], fg='white', relief='flat',
                                        cursor='hand2', command=self.seleccionar_archivo,
                                        activebackground=self.COLORS['primary_light'])
        self.btn_seleccionar.pack(side=tk.RIGHT)
        
        # Salida
        row2 = tk.Frame(frame, bg=self.COLORS['card'])
        row2.pack(fill=tk.X)
        
        tk.Label(row2, text="Salida:", font=self.FONTS['section'], width=8, anchor='w',
                bg=self.COLORS['card'], fg=self.COLORS['primary']).pack(side=tk.LEFT)
        
        self.entry_carpeta = tk.Entry(row2, textvariable=self.carpeta_salida,
                                      font=self.FONTS['body'], state='readonly',
                                      bg=self.COLORS['input_bg'], relief='flat', bd=1)
        self.entry_carpeta.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        
        self.btn_carpeta = tk.Button(row2, text="📁 Cambiar", font=self.FONTS['button'],
                                    bg=self.COLORS['text_secondary'], fg='white', relief='flat',
                                    cursor='hand2', command=self.seleccionar_carpeta,
                                    activebackground='#9E9E9E')
        self.btn_carpeta.pack(side=tk.RIGHT)
    
    def create_validation_bar(self, parent):
        bar = tk.Frame(parent, bg=self.COLORS['surface'], relief='solid', bd=1)
        bar.pack(fill=tk.X, pady=(0, 6))
        
        content = tk.Frame(bar, bg=self.COLORS['surface'])
        content.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_validos = tk.Label(content, text="✓ Válidos: 0", font=self.FONTS['body'],
                                   fg=self.COLORS['success'], bg=self.COLORS['surface'])
        self.lbl_validos.pack(side=tk.LEFT, padx=(0, 12))
        
        self.lbl_invalidos = tk.Label(content, text="✗ Inválidos: 0", font=self.FONTS['body'],
                                     fg=self.COLORS['error'], bg=self.COLORS['surface'])
        self.lbl_invalidos.pack(side=tk.LEFT, padx=(0, 12))
        
        self.lbl_duplicados = tk.Label(content, text="⚠ Duplicados: 0", font=self.FONTS['body'],
                                      fg=self.COLORS['warning'], bg=self.COLORS['surface'])
        self.lbl_duplicados.pack(side=tk.LEFT)
        
        self.lbl_total = tk.Label(content, text="Total: 0", font=self.FONTS['section'],
                                 fg=self.COLORS['primary'], bg=self.COLORS['surface'])
        self.lbl_total.pack(side=tk.RIGHT)
    
    def create_buttons_section(self, parent):
        frame = tk.Frame(parent, bg=self.COLORS['background'])
        frame.pack(fill=tk.X, pady=(0, 6))
        
        self.btn_iniciar = tk.Button(frame, text="▶ INICIAR", font=self.FONTS['button'],
                                    bg=self.COLORS['success'], fg='white', relief='flat',
                                    cursor='hand2', command=self.iniciar_proceso,
                                    state=tk.DISABLED, disabledforeground='#999',
                                    activebackground=self.COLORS['accent'], padx=15, pady=5)
        self.btn_iniciar.pack(side=tk.LEFT, padx=(0, 8))
        
        self.btn_detener = tk.Button(frame, text="■ DETENER", font=self.FONTS['button'],
                                    bg=self.COLORS['error'], fg='white', relief='flat',
                                    cursor='hand2', command=self.detener_proceso,
                                    state=tk.DISABLED, disabledforeground='#999',
                                    activebackground='#EF5350', padx=10, pady=5)
        self.btn_detener.pack(side=tk.LEFT)
        
        self.btn_excel = tk.Button(frame, text="📊 ABRIR EXCEL", font=self.FONTS['button'],
                                  bg=self.COLORS['primary'], fg='white', relief='flat',
                                  cursor='hand2', command=self.generar_excel,
                                  state=tk.DISABLED, disabledforeground='#999',
                                  activebackground=self.COLORS['primary_light'], padx=12, pady=5)
        self.btn_excel.pack(side=tk.RIGHT)
    
    def create_progress_section(self, parent):
        frame = ttk.LabelFrame(parent, text=" Progreso ", style='Card.TLabelframe', padding=10)
        frame.pack(fill=tk.X, pady=(0, 6))
        
        # Porcentaje
        self.lbl_porcentaje = tk.Label(frame, text="0%", font=self.FONTS['porcentaje'],
                                       fg=self.COLORS['text_secondary'], bg=self.COLORS['card'])
        self.lbl_porcentaje.pack()
        
        # Estado
        self.lbl_estado = tk.Label(frame, text="Listo para iniciar", font=self.FONTS['body'],
                                   fg=self.COLORS['text_secondary'], bg=self.COLORS['card'])
        self.lbl_estado.pack(pady=(0, 8))
        
        # Barra de progreso
        barra_frame = tk.Frame(frame, bg=self.COLORS['card'])
        barra_frame.pack(fill=tk.X, padx=5)
        
        self.barra_fondo = tk.Canvas(barra_frame, height=20, bg='#E8E8E8',
                                     highlightthickness=1, highlightbackground='#D0D0D0')
        self.barra_fondo.pack(fill=tk.X)
        
        self.barra_progreso_visual = 0.0
        self.barra_progreso_objetivo = 0.0
        self.barra_ancho = 0
        self.progreso_base = 0
        
        self.barra_fondo.bind('<Configure>', self._on_barra_resize)
        
        # Contador
        self.lbl_progreso = tk.Label(frame, text="0 de 0 facturas", font=self.FONTS['small'],
                                    fg=self.COLORS['text_secondary'], bg=self.COLORS['card'])
        self.lbl_progreso.pack(pady=(6, 0))
        
        self.animacion_barra_activa = False
    
    def _on_barra_resize(self, event):
        self.barra_ancho = event.width - 4
        self._dibujar_barra(self.barra_progreso_visual)
    
    def _dibujar_barra(self, porcentaje):
        self.barra_fondo.delete("all")
        if self.barra_ancho <= 0:
            return
        
        altura = 16
        margen = 2
        ancho_progreso = int((porcentaje / 100) * self.barra_ancho)
        
        if ancho_progreso > 0:
            # Gradiente según porcentaje
            if porcentaje < 30:
                color_inicio, color_fin = (220, 53, 69), (255, 152, 0)
            elif porcentaje < 70:
                color_inicio, color_fin = (255, 152, 0), (156, 204, 101)
            else:
                color_inicio, color_fin = (76, 175, 80), (27, 94, 32)
            
            for i in range(ancho_progreso):
                ratio = i / max(ancho_progreso, 1)
                r = int(color_inicio[0] + (color_fin[0] - color_inicio[0]) * ratio)
                g = int(color_inicio[1] + (color_fin[1] - color_inicio[1]) * ratio)
                b = int(color_inicio[2] + (color_fin[2] - color_inicio[2]) * ratio)
                self.barra_fondo.create_line(i + margen, margen, i + margen, altura + margen,
                                            fill=f'#{r:02x}{g:02x}{b:02x}')
    
    def _iniciar_animacion_barra(self):
        if not self.animacion_barra_activa:
            self.animacion_barra_activa = True
            self._animar_barra()
    
    def _animar_barra(self):
        if not self.animacion_barra_activa:
            return
        
        diferencia = self.barra_progreso_objetivo - self.barra_progreso_visual
        if abs(diferencia) > 0.1:
            incremento = diferencia * 0.12
            if abs(incremento) < 0.2:
                incremento = 0.2 if diferencia > 0 else -0.2
            
            self.barra_progreso_visual += incremento
            if diferencia > 0 and self.barra_progreso_visual > self.barra_progreso_objetivo:
                self.barra_progreso_visual = self.barra_progreso_objetivo
            
            porcentaje = int(self.barra_progreso_visual)
            self._dibujar_barra(self.barra_progreso_visual)
            self.lbl_porcentaje.config(text=f"{porcentaje}%")
            
            # Color del texto
            if porcentaje < 30:
                self.lbl_porcentaje.config(fg='#DC3545')
            elif porcentaje < 70:
                self.lbl_porcentaje.config(fg='#FF9800')
            else:
                self.lbl_porcentaje.config(fg='#2E7D32')
        
        self.after(40, self._animar_barra)
    
    def _detener_animacion_barra(self):
        self.animacion_barra_activa = False
    
    def create_log_section(self, parent):
        frame = ttk.LabelFrame(parent, text=" Registro ", style='Card.TLabelframe', padding=6)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        
        container = tk.Frame(frame, bg=self.COLORS['card'])
        container.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(container, height=6, font=self.FONTS['log'],
                               bg='#FAFAFA', fg=self.COLORS['text_primary'],
                               state=tk.DISABLED, wrap=tk.WORD,
                               yscrollcommand=scrollbar.set, relief='flat', bd=1)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        self.log_text.tag_configure('timestamp', foreground='#9E9E9E')
        self.log_text.tag_configure('success', foreground='#2E7D32')
        self.log_text.tag_configure('error', foreground='#D32F2F')
        self.log_text.tag_configure('warning', foreground='#F57C00')
        self.log_text.tag_configure('info', foreground='#1976D2')
    
    def create_footer(self):
        footer = tk.Frame(self, bg=self.COLORS['surface'], height=28)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        
        # Línea separadora
        tk.Frame(footer, bg=self.COLORS['border'], height=1).pack(fill=tk.X)
        
        content = tk.Frame(footer, bg=self.COLORS['surface'])
        content.pack(fill=tk.BOTH, expand=True, padx=12)
        
        # Empresa (izquierda)
        company = tk.Label(content, text=f"{APP_CONFIG['company']} • {APP_CONFIG['location']}",
                          font=self.FONTS['small'], fg=self.COLORS['text_secondary'],
                          bg=self.COLORS['surface'])
        company.pack(side=tk.LEFT, pady=4)
        
        # Versión y desarrollador (derecha)
        version = tk.Label(content, text=f"v{APP_CONFIG['version']} | {APP_CONFIG['developer']}",
                          font=self.FONTS['small'], fg=self.COLORS['text_secondary'],
                          bg=self.COLORS['surface'])
        version.pack(side=tk.RIGHT, pady=4)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FUNCIONES DE ARCHIVO Y VALIDACIÓN
    # ═══════════════════════════════════════════════════════════════════════════
    
    def seleccionar_archivo(self):
        filetypes = [("Excel", "*.xlsx"), ("Texto", "*.txt"), ("Todos", "*.*")]
        archivo = filedialog.askopenfilename(title="Seleccionar archivo",
                                            filetypes=filetypes,
                                            initialdir=os.path.expanduser("~"))
        if archivo:
            self.archivo_entrada.set(archivo)
            self.validar_archivo(archivo)
    
    def seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Seleccionar carpeta",
                                         initialdir=self.carpeta_salida.get())
        if carpeta:
            self.carpeta_salida.set(carpeta)
            self.add_log(f"Carpeta: {carpeta}", "info")
    
    def validar_archivo(self, archivo):
        self.add_log(f"Archivo: {os.path.basename(archivo)}", "info")
        
        try:
            cufes = []
            ext = os.path.splitext(archivo)[1].lower()
            
            if ext == '.xlsx':
                import pandas as pd
                df = pd.read_excel(archivo, header=None)
                for col in df.columns:
                    for valor in df[col].dropna():
                        texto = str(valor).strip()
                        if len(texto) >= 90:
                            cufes.append(texto)
            else:
                with open(archivo, 'r', encoding='utf-8') as f:
                    cufes = [line.strip() for line in f if line.strip()]
            
            self.validar_cufes(cufes)
        except Exception as e:
            self.add_log(f"Error: {e}", "error")
    
    def validar_cufes(self, cufes):
        import re
        self.cufes_validos = []
        self.cufes_invalidos = []
        cufe_set = set()
        self.duplicados = 0
        
        patron = re.compile(r'^[a-fA-F0-9]{96}$')
        
        for cufe in cufes:
            cufe_limpio = cufe.strip()
            if not patron.match(cufe_limpio):
                self.cufes_invalidos.append(cufe_limpio)
            elif cufe_limpio in cufe_set:
                self.duplicados += 1
            else:
                cufe_set.add(cufe_limpio)
                self.cufes_validos.append(cufe_limpio)
        
        self.lbl_validos.config(text=f"✓ Válidos: {len(self.cufes_validos)}")
        self.lbl_invalidos.config(text=f"✗ Inválidos: {len(self.cufes_invalidos)}")
        self.lbl_duplicados.config(text=f"⚠ Duplicados: {self.duplicados}")
        self.lbl_total.config(text=f"Total: {len(self.cufes_validos)}")
        
        if self.cufes_validos:
            self.btn_iniciar.config(state=tk.NORMAL, bg=self.COLORS['success'])
            self.add_log(f"✓ {len(self.cufes_validos)} CUFEs listos", "success")
        else:
            self.btn_iniciar.config(state=tk.DISABLED)
            self.add_log("No hay CUFEs válidos", "warning")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FUNCIONES DE PROCESO
    # ═══════════════════════════════════════════════════════════════════════════
    
    def iniciar_proceso(self):
        if not self.cufes_validos:
            return
        
        self.processing = True
        self.stop_requested = False
        self.btn_iniciar.config(state=tk.DISABLED, bg=self.COLORS['disabled'])
        self.btn_detener.config(state=tk.NORMAL, bg=self.COLORS['error'])
        self.btn_excel.config(state=tk.DISABLED)
        self.btn_seleccionar.config(state=tk.DISABLED)
        self.btn_carpeta.config(state=tk.DISABLED)
        
        self.total_procesar = len(self.cufes_validos)
        self.progreso_base = 0
        self.barra_progreso_visual = 0.0
        self.barra_progreso_objetivo = 0.0
        self._dibujar_barra(0)
        self.lbl_porcentaje.config(text="0%", fg=self.COLORS['text_secondary'])
        self.lbl_progreso.config(text=f"0 de {self.total_procesar} facturas")
        self.lbl_estado.config(text="Iniciando...")
        
        self._iniciar_animacion_barra()
        self.add_log("Iniciando consulta...", "info")
        
        thread = threading.Thread(target=self.procesar_cufes, daemon=True)
        thread.start()
    
    def procesar_cufes(self):
        try:
            if not MODULOS_DISPONIBLES:
                self.add_log("Error: Módulos no disponibles", "error")
                self.after(0, self.proceso_finalizado)
                return
            
            settings = cargar_settings()
            carpeta_salida = self.carpeta_salida.get()
            
            # Carpeta temporal oculta
            carpeta_temp = os.path.join(carpeta_salida, ".cufe_temp")
            os.makedirs(carpeta_temp, exist_ok=True)
            
            try:
                import platform
                if platform.system() == "Windows":
                    import subprocess
                    subprocess.run(['attrib', '+h', carpeta_temp], check=False, capture_output=True)
            except:
                pass
            
            carpeta_pdfs = os.path.join(carpeta_salida, "Facturas_PDF")
            os.makedirs(carpeta_pdfs, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archivo_excel = os.path.join(carpeta_salida, f"Reporte_{timestamp}.xlsx")
            
            config = {
                'dian_url': settings.dian_url,
                'carpeta_pdfs': carpeta_pdfs,
                'archivo_excel': archivo_excel,
                'num_navegadores': min(len(self.cufes_validos), APP_CONFIG['max_navegadores']),
                'max_reintentos': settings.max_reintentos,
                'carpeta_temp': carpeta_temp,
            }
            
            def callback_progreso(porcentaje, actual, total):
                self.after(0, lambda: self.actualizar_progreso(porcentaje, actual, total))
            
            def callback_mensaje(mensaje, tipo):
                self.add_log(mensaje, tipo)
                self.after(0, lambda: self.lbl_estado.config(text=mensaje[:50]))
            
            resultado = ejecutar_sistema(self.cufes_validos, config,
                                        callback_progreso=callback_progreso,
                                        callback_mensaje=callback_mensaje)
            
            if not self.stop_requested:
                self.resultado_final = resultado
                self.archivo_excel_generado = archivo_excel
                
                resultados = resultado['resultados']
                exitosos = len([r for r in resultados if r['estado'] == 'exitoso'])
                errores = len([r for r in resultados if r['estado'] == 'error'])
                duracion = resultado['duracion']
                
                self.add_log("─" * 35, "info")
                self.add_log(f"COMPLETADO: {exitosos} exitosos, {errores} errores", "success")
                self.add_log(f"Tiempo: {duracion:.1f}s | Excel: {os.path.basename(archivo_excel)}", "info")
                
                self.after(0, lambda: self.actualizar_progreso(100, self.total_procesar, self.total_procesar))
            
            self.after(0, self.proceso_finalizado)
            
        except Exception as e:
            self.add_log(f"Error: {str(e)}", "error")
            self.after(0, self.proceso_finalizado)
    
    def actualizar_progreso(self, porcentaje, actual, total):
        self.progreso_base = actual
        self.lbl_progreso.config(text=f"{actual} de {total} facturas")
        
        objetivo = (actual / max(total, 1)) * 100
        if objetivo > self.barra_progreso_objetivo:
            self.barra_progreso_objetivo = objetivo
        
        if porcentaje >= 100:
            self.barra_progreso_objetivo = 100
            self.barra_progreso_visual = 100
            self._dibujar_barra(100)
            self.lbl_porcentaje.config(text="100%", fg='#1B5E20')
            self.lbl_estado.config(text="¡Completado!")
    
    def proceso_finalizado(self):
        self.processing = False
        self._detener_animacion_barra()
        self.btn_iniciar.config(state=tk.NORMAL, bg=self.COLORS['success'])
        self.btn_detener.config(state=tk.DISABLED, bg=self.COLORS['disabled'])
        self.btn_excel.config(state=tk.NORMAL, bg=self.COLORS['primary'])
        self.btn_seleccionar.config(state=tk.NORMAL)
        self.btn_carpeta.config(state=tk.NORMAL)
    
    def detener_proceso(self):
        if messagebox.askyesno("Confirmar", "¿Detener el proceso?"):
            self.stop_requested = True
            self.add_log("Deteniendo...", "warning")
    
    def generar_excel(self):
        if hasattr(self, 'archivo_excel_generado') and self.archivo_excel_generado:
            if os.path.exists(self.archivo_excel_generado):
                try:
                    import platform
                    if platform.system() == 'Windows':
                        os.startfile(self.archivo_excel_generado)
                    else:
                        import webbrowser
                        webbrowser.open(f'file://{self.archivo_excel_generado}')
                    self.add_log(f"Abriendo Excel...", "success")
                except Exception as e:
                    self.add_log(f"Error: {e}", "error")
            else:
                messagebox.showwarning("Aviso", "Archivo no encontrado")
        else:
            messagebox.showwarning("Aviso", "Ejecute el proceso primero")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FUNCIONES DE LOG
    # ═══════════════════════════════════════════════════════════════════════════
    
    def add_log(self, mensaje, tipo="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((timestamp, mensaje, tipo))
    
    def process_log_queue(self):
        try:
            while True:
                timestamp, mensaje, tipo = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{timestamp}] ", 'timestamp')
                self.log_text.insert(tk.END, f"{mensaje}\n", tipo)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self.process_log_queue)
    
    def on_close(self):
        if self.processing:
            if not messagebox.askyesno("Confirmar", "¿Salir? Hay un proceso activo."):
                return
            self.stop_requested = True
        self.destroy()


def main():
    print("=" * 50)
    print("  SISTEMA DE CONSULTA CUFE - DIAN")
    print(f"  v{APP_CONFIG['version']} | {APP_CONFIG['developer']}")
    print("=" * 50)
    
    app = ConsultaCUFEApp()
    app.mainloop()


if __name__ == "__main__":
    main()