"""
Sistema de Consulta CUFE DIAN - Interfaz Gráfica v4.2.0
Desarrollado por C.G. (Cristhian Guerrero)
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
    'version': '4.2.0',
    'company': 'A.S. Contadores & Asesores SAS',
    'location': 'Pasto, Nariño - Colombia',
    'developer': '© C. Guerrero',
    'width': 900,
    'height': 720,
    'max_navegadores': 10,
}


class ConsultaCUFEApp(tk.Tk):
    """Interfaz Profesional para Consulta CUFE DIAN - v4.2.0 Rediseñada"""
    
    def __init__(self):
        super().__init__()
        
        self.title(APP_CONFIG['title'])
        self.processing = False
        self.stop_requested = False
        
        # Colores institucionales
        self.COLORS = {
            'primary': '#2E7D32',
            'primary_light': '#4CAF50',
            'primary_dark': '#1B5E20',
            'background': '#FFFFFF',
            'surface': '#F5F5F5',
            'text_primary': '#1A1A1A',
            'text_secondary': '#616161',
            'text_light': '#FFFFFF',
            'success': '#2E7D32',
            'warning': '#F57C00',
            'error': '#C62828',
            'border': '#E0E0E0',
            'disabled': '#BDBDBD',
            'input_bg': '#F8F9FA',
        }
        
        self.FONTS = {
            'title': ('Arial', 18, 'bold'),
            'subtitle': ('Arial', 11),
            'section': ('Arial', 10, 'bold'),
            'body': ('Arial', 10),
            'button': ('Arial', 9, 'bold'),
            'small': ('Arial', 9),
            'log': ('Consolas', 9),
            'porcentaje': ('Arial', 36, 'bold'),
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
        self.total_lotes = 0
        self.resultado_final = None
        self.archivo_excel_generado = None
        
        self.log_queue = queue.Queue()
        
        # Tamaño fijo (no redimensionable para evitar problemas de layout)
        self.geometry(f"{APP_CONFIG['width']}x{APP_CONFIG['height']}")
        self.resizable(False, False)
        self.configure(bg=self.COLORS['background'])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.setup_icon()
        self.center_window()
        self.setup_styles()
        self.create_ui()
        self.process_log_queue()
    
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)
    
    def center_window(self):
        self.update_idletasks()
        width = APP_CONFIG['width']
        height = APP_CONFIG['height']
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def setup_icon(self):
        try:
            import platform
            sistema = platform.system()
            
            if sistema == "Windows":
                icon_path = self.resource_path("assets/dian.ico")
                if os.path.exists(icon_path):
                    try:
                        self.iconbitmap(icon_path)
                        return
                    except:
                        pass
            
            logo_path = self.resource_path("assets/logo.png")
            if os.path.exists(logo_path):
                pil_image = Image.open(logo_path)
                icon_48 = pil_image.resize((48, 48), Image.Resampling.LANCZOS)
                icon_32 = pil_image.resize((32, 32), Image.Resampling.LANCZOS)
                icon_tk_48 = ImageTk.PhotoImage(icon_48)
                icon_tk_32 = ImageTk.PhotoImage(icon_32)
                self.iconphoto(True, icon_tk_48, icon_tk_32)
                self._icon_refs = [icon_tk_48, icon_tk_32]
                
        except Exception as e:
            print(f"Aviso: No se pudo cargar el ícono: {e}")
    
    def load_logo(self, max_width=280, max_height=60):
        try:
            logo_path = self.resource_path("assets/logo.png")
            if not os.path.exists(logo_path):
                return None
            
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
            return None
    
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.style.configure('Header.TFrame', background=self.COLORS['primary'])
        self.style.configure('Main.TFrame', background=self.COLORS['background'])
        self.style.configure('Card.TFrame', background=self.COLORS['background'])
        
        self.style.configure('Header.TLabel', background=self.COLORS['primary'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['title'])
        self.style.configure('HeaderSub.TLabel', background=self.COLORS['primary'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['subtitle'])
        self.style.configure('Section.TLabel', background=self.COLORS['background'],
                           foreground=self.COLORS['primary'], font=self.FONTS['section'])
        self.style.configure('Body.TLabel', background=self.COLORS['background'],
                           foreground=self.COLORS['text_primary'], font=self.FONTS['body'])
        self.style.configure('Small.TLabel', background=self.COLORS['background'],
                           foreground=self.COLORS['text_secondary'], font=self.FONTS['small'])
        self.style.configure('Success.TLabel', background=self.COLORS['background'],
                           foreground=self.COLORS['success'], font=self.FONTS['body'])
        self.style.configure('Error.TLabel', background=self.COLORS['background'],
                           foreground=self.COLORS['error'], font=self.FONTS['body'])
        
        self.style.configure('Card.TLabelframe', background=self.COLORS['background'],
                           borderwidth=1, relief='solid')
        self.style.configure('Card.TLabelframe.Label', background=self.COLORS['background'],
                           foreground=self.COLORS['primary'], font=self.FONTS['section'])
        
        self.style.configure('Primary.TButton', background=self.COLORS['primary'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['button'],
                           padding=(15, 8))
        self.style.map('Primary.TButton',
                      background=[('active', self.COLORS['primary_light']),
                                ('pressed', self.COLORS['primary_dark']),
                                ('disabled', self.COLORS['disabled'])])
        
        self.style.configure('Secondary.TButton', background=self.COLORS['text_secondary'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['button'],
                           padding=(10, 6))
        self.style.map('Secondary.TButton',
                      background=[('active', '#757575'), ('disabled', self.COLORS['disabled'])])
        
        self.style.configure('Success.TButton', background=self.COLORS['success'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['button'],
                           padding=(15, 8))
        self.style.map('Success.TButton',
                      background=[('active', self.COLORS['primary_light']),
                                ('disabled', self.COLORS['disabled'])])
        
        self.style.configure('Danger.TButton', background=self.COLORS['error'],
                           foreground=self.COLORS['text_light'], font=self.FONTS['button'],
                           padding=(10, 6))
        self.style.map('Danger.TButton',
                      background=[('active', '#EF5350'), ('disabled', self.COLORS['disabled'])])
    
    def create_ui(self):
        self.create_header()
        self.create_main_content()
        self.create_footer()
    
    def create_header(self):
        header = ttk.Frame(self, style='Header.TFrame')
        header.pack(fill=tk.X)
        
        header_content = ttk.Frame(header, style='Header.TFrame')
        header_content.pack(fill=tk.X, padx=20, pady=10)
        
        logo = self.load_logo(max_width=280, max_height=55)
        if logo:
            self._logo_ref = logo
            logo_label = ttk.Label(header_content, image=logo, style='Header.TLabel')
            logo_label.pack(side=tk.LEFT)
        else:
            company_label = ttk.Label(header_content, text="A.S. CONTADORES & ASESORES SAS",
                                     style='Header.TLabel')
            company_label.pack(side=tk.LEFT)
        
        title_frame = ttk.Frame(header_content, style='Header.TFrame')
        title_frame.pack(side=tk.RIGHT)
        
        title = ttk.Label(title_frame, text="Sistema de Consulta CUFE", style='Header.TLabel')
        title.pack(anchor='e')
        
        subtitle = ttk.Label(title_frame, text="Facturación Electrónica DIAN", style='HeaderSub.TLabel')
        subtitle.pack(anchor='e')
    
    def create_main_content(self):
        main = ttk.Frame(self, style='Main.TFrame')
        main.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Sección compacta de entrada/salida
        self.create_io_section(main)
        
        # Validación compacta
        self.create_validation_section(main)
        
        # Controles
        self.create_controls_section(main)
        
        # Progreso con barra animada
        self.create_progress_section(main)
        
        # Log expandido
        self.create_log_section(main)
    
    def create_io_section(self, parent):
        """Sección compacta de entrada y salida en una sola card"""
        frame = ttk.LabelFrame(parent, text="  Configuración  ", 
                              style='Card.TLabelframe', padding=10)
        frame.pack(fill=tk.X, pady=(0, 8))
        
        # Fila 1: Archivo de entrada
        row1 = ttk.Frame(frame, style='Card.TFrame')
        row1.pack(fill=tk.X, pady=(0, 6))
        
        ttk.Label(row1, text="Entrada:", style='Section.TLabel', width=8).pack(side=tk.LEFT)
        
        self.entry_archivo = ttk.Entry(row1, textvariable=self.archivo_entrada,
                                       state='readonly', font=self.FONTS['small'])
        self.entry_archivo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 8))
        
        self.btn_seleccionar = ttk.Button(row1, text="📁 Seleccionar",
                                         command=self.seleccionar_archivo, style='Primary.TButton')
        self.btn_seleccionar.pack(side=tk.RIGHT)
        
        # Fila 2: Carpeta de salida
        row2 = ttk.Frame(frame, style='Card.TFrame')
        row2.pack(fill=tk.X)
        
        ttk.Label(row2, text="Salida:", style='Section.TLabel', width=8).pack(side=tk.LEFT)
        
        self.entry_carpeta = ttk.Entry(row2, textvariable=self.carpeta_salida,
                                       state='readonly', font=self.FONTS['small'])
        self.entry_carpeta.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 8))
        
        self.btn_carpeta = ttk.Button(row2, text="📁 Cambiar",
                                     command=self.seleccionar_carpeta, style='Secondary.TButton')
        self.btn_carpeta.pack(side=tk.RIGHT)
    
    def create_validation_section(self, parent):
        """Sección de validación compacta en una línea"""
        frame = ttk.Frame(parent, style='Card.TFrame')
        frame.pack(fill=tk.X, pady=(0, 8))
        
        # Contenedor con borde
        inner = tk.Frame(frame, bg=self.COLORS['surface'], relief='solid', bd=1)
        inner.pack(fill=tk.X)
        
        content = tk.Frame(inner, bg=self.COLORS['surface'])
        content.pack(fill=tk.X, padx=10, pady=6)
        
        self.lbl_validos = tk.Label(content, text="✓ Válidos: 0", 
                                    font=self.FONTS['body'], fg=self.COLORS['success'],
                                    bg=self.COLORS['surface'])
        self.lbl_validos.pack(side=tk.LEFT, padx=(0, 15))
        
        self.lbl_invalidos = tk.Label(content, text="✗ Inválidos: 0", 
                                      font=self.FONTS['body'], fg=self.COLORS['error'],
                                      bg=self.COLORS['surface'])
        self.lbl_invalidos.pack(side=tk.LEFT, padx=(0, 15))
        
        self.lbl_duplicados = tk.Label(content, text="⚠ Duplicados: 0", 
                                       font=self.FONTS['body'], fg=self.COLORS['warning'],
                                       bg=self.COLORS['surface'])
        self.lbl_duplicados.pack(side=tk.LEFT)
        
        self.lbl_total = tk.Label(content, text="Total a procesar: 0", 
                                  font=self.FONTS['section'], fg=self.COLORS['primary'],
                                  bg=self.COLORS['surface'])
        self.lbl_total.pack(side=tk.RIGHT)
    
    def create_controls_section(self, parent):
        """Botones de control"""
        frame = ttk.Frame(parent, style='Card.TFrame')
        frame.pack(fill=tk.X, pady=(0, 8))
        
        self.btn_iniciar = ttk.Button(frame, text="▶ INICIAR",
                                     command=self.iniciar_proceso, style='Success.TButton',
                                     state=tk.DISABLED)
        self.btn_iniciar.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_detener = ttk.Button(frame, text="■ DETENER",
                                     command=self.detener_proceso, style='Danger.TButton',
                                     state=tk.DISABLED)
        self.btn_detener.pack(side=tk.LEFT)
        
        self.btn_excel = ttk.Button(frame, text="📊 ABRIR EXCEL",
                                   command=self.generar_excel, style='Primary.TButton',
                                   state=tk.DISABLED)
        self.btn_excel.pack(side=tk.RIGHT)
    
    def create_progress_section(self, parent):
        """Sección de progreso con barra animada colorida"""
        frame = ttk.LabelFrame(parent, text="  Progreso  ", 
                              style='Card.TLabelframe', padding=12)
        frame.pack(fill=tk.X, pady=(0, 8))
        
        # Porcentaje grande
        self.lbl_porcentaje = tk.Label(frame, text="0%", font=self.FONTS['porcentaje'],
                                       fg=self.COLORS['text_secondary'], bg=self.COLORS['background'])
        self.lbl_porcentaje.pack()
        
        # Estado actual
        self.lbl_estado = tk.Label(frame, text="Listo para iniciar",
                                   font=self.FONTS['body'], fg=self.COLORS['text_secondary'],
                                   bg=self.COLORS['background'])
        self.lbl_estado.pack(pady=(2, 10))
        
        # Frame para la barra personalizada
        barra_frame = tk.Frame(frame, bg=self.COLORS['background'])
        barra_frame.pack(fill=tk.X, padx=10)
        
        # Barra de fondo con bordes redondeados (simulados)
        self.barra_fondo = tk.Canvas(barra_frame, height=24, bg='#E8E8E8',
                                     highlightthickness=1, highlightbackground='#D0D0D0')
        self.barra_fondo.pack(fill=tk.X)
        
        # Variables de progreso
        self.barra_progreso_valor = 0
        self.barra_progreso_visual = 0.0
        self.barra_progreso_objetivo = 0.0
        self.barra_ancho = 0
        
        # Contadores para progreso granular
        self.progreso_base = 0
        self.progreso_parcial = 0.0
        self.fase_actual = 0
        
        # Bind para redimensionar
        self.barra_fondo.bind('<Configure>', self._on_barra_resize)
        
        # Contador de facturas
        self.lbl_progreso = tk.Label(frame, text="0 de 0 facturas procesadas",
                                    font=self.FONTS['small'], fg=self.COLORS['text_secondary'],
                                    bg=self.COLORS['background'])
        self.lbl_progreso.pack(pady=(8, 0))
        
        # Variables para animación
        self.animacion_activa = False
        self.animacion_barra_activa = False
    
    def _on_barra_resize(self, event):
        self.barra_ancho = event.width - 4
        self._dibujar_barra(self.barra_progreso_visual)
    
    def _dibujar_barra(self, porcentaje):
        """Dibuja la barra de progreso con gradiente dinámico según el porcentaje"""
        self.barra_fondo.delete("all")
        
        if self.barra_ancho <= 0:
            return
        
        altura = 20
        margen = 2
        ancho_progreso = int((porcentaje / 100) * self.barra_ancho)
        
        if ancho_progreso > 0:
            # Colores del gradiente según el porcentaje
            if porcentaje < 30:
                # Rojo -> Naranja
                color_inicio = (220, 53, 69)    # Rojo
                color_fin = (255, 152, 0)       # Naranja
            elif porcentaje < 70:
                # Naranja -> Amarillo verdoso
                color_inicio = (255, 152, 0)    # Naranja
                color_fin = (156, 204, 101)     # Verde claro
            else:
                # Verde claro -> Verde oscuro
                color_inicio = (76, 175, 80)    # Verde
                color_fin = (27, 94, 32)        # Verde oscuro
            
            # Dibujar gradiente horizontal
            for i in range(ancho_progreso):
                ratio = i / max(ancho_progreso, 1)
                r = int(color_inicio[0] + (color_fin[0] - color_inicio[0]) * ratio)
                g = int(color_inicio[1] + (color_fin[1] - color_inicio[1]) * ratio)
                b = int(color_inicio[2] + (color_fin[2] - color_inicio[2]) * ratio)
                color = f'#{r:02x}{g:02x}{b:02x}'
                self.barra_fondo.create_line(i + margen, margen, i + margen, altura + margen, fill=color)
            
            # Efecto de brillo en la parte superior
            if ancho_progreso > 5:
                for i in range(min(ancho_progreso, self.barra_ancho)):
                    brillo_ratio = 0.3 * (1 - (i / ancho_progreso) * 0.5)
                    self.barra_fondo.create_line(
                        i + margen, margen, i + margen, margen + 4,
                        fill=f'#{int(255*brillo_ratio):02x}{int(255*brillo_ratio):02x}{int(255*brillo_ratio):02x}'
                    )
    
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
            elif diferencia < 0 and self.barra_progreso_visual < self.barra_progreso_objetivo:
                self.barra_progreso_visual = self.barra_progreso_objetivo
            
            porcentaje_mostrar = int(self.barra_progreso_visual)
            self._dibujar_barra(self.barra_progreso_visual)
            self.lbl_porcentaje.config(text=f"{porcentaje_mostrar}%")
            
            # Color del texto según porcentaje
            if porcentaje_mostrar < 30:
                self.lbl_porcentaje.config(fg='#DC3545')  # Rojo
            elif porcentaje_mostrar < 70:
                self.lbl_porcentaje.config(fg='#FF9800')  # Naranja
            else:
                self.lbl_porcentaje.config(fg='#2E7D32')  # Verde
        
        self.after(40, self._animar_barra)
    
    def _detener_animacion_barra(self):
        self.animacion_barra_activa = False
    
    def _calcular_progreso_por_fase(self, mensaje):
        fases = {
            'Conectando': 0.5,
            'Conexión establecida': 1.0,
            'Preparando': 0.8,
            'Consultando': 2.5,
            'descargada': 4.0,
            'No registrada': 4.0,
            'recuperada': 4.0,
            'Verificando': 1.5,
            'completadas': 2.0,
            'Generando': 1.0,
            'finalizado': 1.0,
        }
        
        incremento = 0
        for clave, peso in fases.items():
            if clave.lower() in mensaje.lower():
                incremento = peso
                break
        
        return incremento
    
    def _actualizar_progreso_parcial(self, mensaje):
        if not self.processing:
            return
        
        incremento = self._calcular_progreso_por_fase(mensaje)
        
        if incremento > 0:
            import random
            variacion = random.uniform(-0.3, 0.5)
            incremento += variacion
            
            nuevo_objetivo = self.barra_progreso_objetivo + incremento
            
            max_progreso = (self.progreso_base / max(self.total_procesar, 1)) * 100 + 15
            if nuevo_objetivo > min(99, max_progreso):
                nuevo_objetivo = min(99, max_progreso)
            
            self.barra_progreso_objetivo = nuevo_objetivo
    
    def create_log_section(self, parent):
        """Sección de log expandida"""
        frame = ttk.LabelFrame(parent, text="  Registro de Actividad  ", 
                              style='Card.TLabelframe', padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        log_container = ttk.Frame(frame, style='Card.TFrame')
        log_container.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_container, height=10, font=self.FONTS['log'],
                               bg='#FAFAFA', fg=self.COLORS['text_primary'],
                               state=tk.DISABLED, wrap=tk.WORD,
                               yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        self.log_text.tag_configure('timestamp', foreground='#757575')
        self.log_text.tag_configure('success', foreground='#2E7D32')
        self.log_text.tag_configure('error', foreground='#C62828')
        self.log_text.tag_configure('warning', foreground='#F57C00')
        self.log_text.tag_configure('info', foreground='#1565C0')
    
    def create_footer(self):
        footer = ttk.Frame(self, style='Main.TFrame')
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        separator = ttk.Separator(footer, orient='horizontal')
        separator.pack(fill=tk.X)
        
        footer_content = ttk.Frame(footer, style='Main.TFrame')
        footer_content.pack(fill=tk.X, padx=15, pady=8)
        
        # Izquierda: Empresa
        company = ttk.Label(footer_content,
                           text=f"{APP_CONFIG['company']} • {APP_CONFIG['location']}",
                           style='Small.TLabel')
        company.pack(side=tk.LEFT)
        
        # Derecha: Versión y desarrollador
        version_dev = ttk.Label(footer_content, 
                               text=f"v{APP_CONFIG['version']} | {APP_CONFIG['developer']}",
                               style='Small.TLabel')
        version_dev.pack(side=tk.RIGHT)
    
    def seleccionar_archivo(self):
        filetypes = [("Archivos Excel", "*.xlsx"), ("Archivos de texto", "*.txt"),
                    ("Todos los archivos", "*.*")]
        
        archivo = filedialog.askopenfilename(title="Seleccionar archivo de CUFEs",
                                            filetypes=filetypes,
                                            initialdir=os.path.expanduser("~"))
        if archivo:
            self.archivo_entrada.set(archivo)
            self.validar_archivo(archivo)
    
    def seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Seleccionar carpeta de salida",
                                         initialdir=self.carpeta_salida.get())
        if carpeta:
            self.carpeta_salida.set(carpeta)
            self.add_log(f"Carpeta de salida: {carpeta}", "info")
    
    def validar_archivo(self, archivo):
        self.add_log(f"Procesando: {os.path.basename(archivo)}", "info")
        
        try:
            cufes = []
            extension = os.path.splitext(archivo)[1].lower()
            
            if extension == '.xlsx':
                try:
                    import pandas as pd
                    df = pd.read_excel(archivo, header=None)
                    for col in df.columns:
                        for valor in df[col].dropna():
                            texto = str(valor).strip()
                            if len(texto) >= 90:
                                cufes.append(texto)
                except Exception as e:
                    self.add_log(f"Error leyendo Excel: {e}", "error")
                    return
            else:
                with open(archivo, 'r', encoding='utf-8') as f:
                    cufes = [line.strip() for line in f if line.strip()]
            
            self.lista_cufes = cufes
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
        self.lbl_total.config(text=f"Total a procesar: {len(self.cufes_validos)}")
        
        if self.cufes_validos:
            self.btn_iniciar.config(state=tk.NORMAL)
            self.add_log(f"✓ {len(self.cufes_validos)} CUFEs listos para procesar", "success")
        else:
            self.btn_iniciar.config(state=tk.DISABLED)
            self.add_log("No hay CUFEs válidos", "warning")
        
        if self.cufes_invalidos:
            self.add_log(f"⚠ {len(self.cufes_invalidos)} CUFEs con formato inválido", "warning")
    
    def iniciar_proceso(self):
        if not self.cufes_validos:
            messagebox.showwarning("Aviso", "No hay CUFEs válidos para procesar")
            return
        
        self.processing = True
        self.stop_requested = False
        self.btn_iniciar.config(state=tk.DISABLED)
        self.btn_detener.config(state=tk.NORMAL)
        self.btn_excel.config(state=tk.DISABLED)
        self.btn_seleccionar.config(state=tk.DISABLED)
        self.btn_carpeta.config(state=tk.DISABLED)
        
        self.total_procesar = len(self.cufes_validos)
        self.progreso_base = 0
        self.barra_progreso_visual = 0.0
        self.barra_progreso_objetivo = 0.0
        self._dibujar_barra(0)
        self.lbl_porcentaje.config(text="0%", fg=self.COLORS['text_secondary'])
        self.lbl_progreso.config(text=f"0 de {self.total_procesar} facturas procesadas")
        self.lbl_estado.config(text="Iniciando consulta...")
        
        self._iniciar_animacion_barra()
        
        self.add_log("Iniciando consulta de facturas...", "info")
        
        thread = threading.Thread(target=self.procesar_cufes, daemon=True)
        thread.start()
    
    def procesar_cufes(self):
        try:
            if not MODULOS_DISPONIBLES:
                self.add_log("Error: Módulos del sistema no disponibles", "error")
                self.after(0, self.proceso_finalizado)
                return
            
            settings = cargar_settings()
            
            carpeta_salida = self.carpeta_salida.get()
            
            # Crear carpeta oculta para temporales
            carpeta_temp = os.path.join(carpeta_salida, ".cufe_temp")
            os.makedirs(carpeta_temp, exist_ok=True)
            
            # En Windows, ocultar la carpeta
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
            archivo_excel = os.path.join(carpeta_salida, f"Reporte_Facturas_{timestamp}.xlsx")
            
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
                self.after(0, lambda m=mensaje: self.lbl_estado.config(text=m))
                self.after(0, lambda m=mensaje: self._actualizar_progreso_parcial(m))
            
            resultado = ejecutar_sistema(self.cufes_validos, config,
                                        callback_progreso=callback_progreso,
                                        callback_mensaje=callback_mensaje)
            
            if self.stop_requested:
                self.add_log("Proceso detenido por el usuario", "warning")
                self.after(0, lambda: self.lbl_estado.config(text="Proceso detenido"))
            else:
                self.resultado_final = resultado
                self.archivo_excel_generado = archivo_excel
                
                resultados = resultado['resultados']
                exitosos = len([r for r in resultados if r['estado'] == 'exitoso'])
                no_encontrados = len([r for r in resultados if r['estado'] == 'no_encontrado'])
                errores = len([r for r in resultados if r['estado'] == 'error'])
                duracion = resultado['duracion']
                
                self.add_log("─" * 40, "info")
                self.add_log("RESUMEN FINAL:", "info")
                self.add_log(f"  Exitosos: {exitosos}", "success")
                self.add_log(f"  No encontrados: {no_encontrados}", "warning")
                self.add_log(f"  Errores: {errores}", "error")
                self.add_log(f"  Tiempo total: {duracion:.1f} segundos", "info")
                self.add_log(f"  Excel: {os.path.basename(archivo_excel)}", "success")
                self.add_log("─" * 40, "info")
                
                self.after(0, lambda: self.actualizar_progreso(100, self.total_procesar, self.total_procesar))
            
            self.after(0, self.proceso_finalizado)
            
        except Exception as e:
            self.add_log(f"Error: {str(e)}", "error")
            self.after(0, lambda: self.lbl_estado.config(text="Error en el proceso"))
            self.after(0, self.proceso_finalizado)
    
    def actualizar_progreso(self, porcentaje, actual, total):
        self.progreso_base = actual
        self.lbl_progreso.config(text=f"{actual} de {total} facturas procesadas")
        
        objetivo_real = (actual / max(total, 1)) * 100
        
        if objetivo_real > self.barra_progreso_objetivo:
            self.barra_progreso_objetivo = objetivo_real
        
        if porcentaje >= 100:
            self.barra_progreso_objetivo = 100
            self.barra_progreso_visual = 100
            self._dibujar_barra(100)
            self.lbl_porcentaje.config(text="100%", fg='#1B5E20')
            self.lbl_estado.config(text="¡Proceso completado!")
    
    def proceso_finalizado(self):
        self.processing = False
        self._detener_animacion_barra()
        self.btn_iniciar.config(state=tk.NORMAL)
        self.btn_detener.config(state=tk.DISABLED)
        self.btn_excel.config(state=tk.NORMAL)
        self.btn_seleccionar.config(state=tk.NORMAL)
        self.btn_carpeta.config(state=tk.NORMAL)
    
    def detener_proceso(self):
        respuesta = messagebox.askyesno("Confirmar",
            "¿Está seguro que desea detener el proceso?\n\n"
            "Los documentos ya descargados se conservarán.")
        
        if respuesta:
            self.stop_requested = True
            self.add_log("Deteniendo proceso...", "warning")
    
    def generar_excel(self):
        if hasattr(self, 'archivo_excel_generado') and self.archivo_excel_generado and os.path.exists(self.archivo_excel_generado):
            try:
                import webbrowser
                import platform
                
                archivo = self.archivo_excel_generado
                
                if platform.system() == 'Windows':
                    os.startfile(archivo)
                elif platform.system() == 'Darwin':
                    os.system(f'open "{archivo}"')
                else:
                    webbrowser.open(f'file://{archivo}')
                
                self.add_log(f"Abriendo: {os.path.basename(archivo)}", "success")
                
            except Exception as e:
                self.add_log(f"Error abriendo archivo: {e}", "error")
                messagebox.showinfo("Reporte Excel",
                    f"El reporte se guardó en:\n{self.archivo_excel_generado}")
        else:
            messagebox.showwarning("Aviso",
                "No hay reporte Excel generado.\nEjecute el proceso primero.")
    
    def add_log(self, mensaje, tipo="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((timestamp, mensaje, tipo))
    
    def process_log_queue(self):
        try:
            while True:
                timestamp, mensaje, tipo = self.log_queue.get_nowait()
                self._write_log(timestamp, mensaje, tipo)
        except queue.Empty:
            pass
        self.after(100, self.process_log_queue)
    
    def _write_log(self, timestamp, mensaje, tipo):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] ", 'timestamp')
        self.log_text.insert(tk.END, f"{mensaje}\n", tipo)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def on_close(self):
        if self.processing:
            respuesta = messagebox.askyesno("Confirmar salida",
                "Hay un proceso en ejecución.\n\n"
                "¿Está seguro que desea salir?")
            if not respuesta:
                return
            self.stop_requested = True
        self.destroy()


def main():
    print("=" * 60)
    print("  SISTEMA DE CONSULTA CUFE - DIAN")
    print("  A.S. Contadores & Asesores SAS")
    print(f"  Versión {APP_CONFIG['version']} | Dev: {APP_CONFIG['developer']}")
    print("=" * 60)
    
    try:
        app = ConsultaCUFEApp()
        app.mainloop()
    except Exception as e:
        print(f"Error crítico: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()